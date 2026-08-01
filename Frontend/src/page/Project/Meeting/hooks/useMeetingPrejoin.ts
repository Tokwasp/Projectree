import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Room,
  createLocalTracks,
  type LocalAudioTrack,
  type LocalTrack,
  type LocalVideoTrack,
} from "livekit-client";
import { join } from "../api/meetingApi";
import { useMeetingStore } from "../../../../store/meetingStore";
import { connectMeeting } from "../../../../utils/meetingSession";
import { useMicLevel } from "./useMicLevel";

export const useMeetingPrejoin = (projectId: number) => {
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [microphones, setMicrophones] = useState<MediaDeviceInfo[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [microphoneId, setMicrophoneId] = useState("");
  const [camTrack, setCamTrack] = useState<LocalVideoTrack | null>(null);
  const [micTrack, setMicTrack] = useState<LocalAudioTrack | null>(null);
  const [camOn, setCamOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const [error, setError] = useState("");
  const [joining, setJoining] = useState(false);
  const [camBusy, setCamBusy] = useState(false);
  const [micBusy, setMicBusy] = useState(false);

  const [previewEl, setPreviewEl] = useState<HTMLVideoElement | null>(null);
  const previewRef = useCallback((element: HTMLVideoElement | null) => {
    setPreviewEl(element);
  }, []);

  const tracksRef = useRef<LocalTrack[]>([]);
  const handedOffRef = useRef(false);
  const camPendingRef = useRef(false);
  const micPendingRef = useRef(false);

  const micLevel = useMicLevel(micTrack, micOn);

  const navigate = useNavigate();
  const startConnecting = useMeetingStore((state) => state.startConnecting);
  const reset = useMeetingStore((state) => state.reset);

  const loadDevices = async () => {
    setMicrophones(await Room.getLocalDevices("audioinput", false));
    setCameras(await Room.getLocalDevices("videoinput", false));
  };

  useEffect(() => {
    Room.getLocalDevices("audioinput", false).then(setMicrophones);
    Room.getLocalDevices("videoinput", false).then(setCameras);

    return () => {
      if (!handedOffRef.current) {
        tracksRef.current.forEach((track) => {
          track.detach();
          track.stop();
        });
      }
      tracksRef.current = [];
    };
  }, []);

  useEffect(() => {
    if (!camTrack || !previewEl || !camOn) return;

    camTrack.attach(previewEl);
    return () => {
      camTrack.detach(previewEl);
    };
  }, [camTrack, previewEl, camOn]);

  const toggleMic = async () => {
    if (micPendingRef.current) return;
    micPendingRef.current = true;
    setMicBusy(true);

    try {
      if (micTrack) {
        const next = !micOn;
        if (next) await micTrack.unmute();
        else await micTrack.mute();
        setMicOn(next);
        return;
      }

      const [audio] = await createLocalTracks({
        audio: microphoneId ? { deviceId: microphoneId } : true,
      });
      const track = audio as LocalAudioTrack;

      tracksRef.current.push(track);
      setMicTrack(track);
      setMicrophoneId(track.mediaStreamTrack.getSettings().deviceId ?? "");
      setMicOn(true);
      setError("");
      await loadDevices();
    } catch {
      setError("마이크 권한을 허용해 주세요.");
    } finally {
      micPendingRef.current = false;
      setMicBusy(false);
    }
  };

  const toggleCam = async () => {
    if (camPendingRef.current) return;
    camPendingRef.current = true;
    setCamBusy(true);

    try {
      if (camTrack) {
        const next = !camOn;
        if (next) await camTrack.unmute();
        else await camTrack.mute();
        setCamOn(next);
        return;
      }

      const [video] = await createLocalTracks({
        video: cameraId ? { deviceId: cameraId } : true,
      });
      const track = video as LocalVideoTrack;

      tracksRef.current.push(track);
      setCamTrack(track);
      setCameraId(track.mediaStreamTrack.getSettings().deviceId ?? "");
      setCamOn(true);
      setError("");
      await loadDevices();
    } catch {
      setError("카메라를 사용할 수 없습니다. 권한과 기기를 확인해 주세요.");
    } finally {
      camPendingRef.current = false;
      setCamBusy(false);
    }
  };

  const changeMicrophone = async (deviceId: string) => {
    const previous = microphoneId;
    setMicrophoneId(deviceId);
    if (!micTrack) return;

    try {
      const applied = await micTrack.setDeviceId({ exact: deviceId });
      if (!applied) setError("선택한 마이크로 전환하지 못했습니다.");
      else setError("");
    } catch {
      setMicrophoneId(previous);
      setError("선택한 마이크를 사용할 수 없습니다.");
    }
  };

  const changeCamera = async (deviceId: string) => {
    const previous = cameraId;
    setCameraId(deviceId);
    if (!camTrack) return;

    try {
      const applied = await camTrack.setDeviceId({ exact: deviceId });
      if (!applied) setError("선택한 카메라로 전환하지 못했습니다.");
      else setError("");
    } catch {
      setCameraId(previous);
      setError("선택한 카메라를 사용할 수 없습니다.");
    }
  };

  const submit = async () => {
    if (joining) return;

    setJoining(true);
    setError("");

    const acquired = tracksRef.current;

    try {
      const info = await join(projectId);
      // const info = await join();

      handedOffRef.current = true;
      startConnecting(projectId);

      if (!micOn && micTrack) micTrack.stop();
      if (!camOn && camTrack) camTrack.stop();

      await connectMeeting({
        info,
        micTrack: micOn ? micTrack : null,
        camTrack: camOn ? camTrack : null,
        micDeviceId: microphoneId,
        camDeviceId: cameraId,
      });
    } catch (caught) {
      if (handedOffRef.current) {
        acquired.forEach((track) => {
          track.detach();
          track.stop();
        });
      }

      handedOffRef.current = false;
      reset();
      setError(
        caught instanceof Error ? caught.message : "회의 참여에 실패했습니다.",
      );
    } finally {
      setJoining(false);
    }
  };

  const cancel = () => navigate(`/projects/${projectId}`, { replace: true });

  return {
    cameras,
    microphones,
    cameraId,
    microphoneId,
    camTrack,
    micTrack,
    camOn,
    micOn,
    camBusy,
    micBusy,
    micLevel,
    error,
    joining,
    previewRef,
    toggleCam,
    toggleMic,
    changeCamera,
    changeMicrophone,
    submit,
    cancel,
  };
};
