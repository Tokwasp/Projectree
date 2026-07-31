import { useEffect, useRef, useState } from "react";
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

  const previewRef = useRef<HTMLVideoElement | null>(null);
  const tracksRef = useRef<LocalTrack[]>([]);
  const handedOffRef = useRef(false);

  const navigate = useNavigate();
  const startConnecting = useMeetingStore((state) => state.startConnecting);
  const reset = useMeetingStore((state) => state.reset);

  // 두 번째 인자를 false로 넘겨야 권한 요청 없이 조회만 한다 (기본값은 요청함)
  const loadDevices = async () => {
    setMicrophones(await Room.getLocalDevices("audioinput", false));
    setCameras(await Room.getLocalDevices("videoinput", false));
  };

  // 마운트 시에는 카메라·마이크를 잡지 않는다 — 사용자가 켤 때만 잡는다
  useEffect(() => {
    Room.getLocalDevices("audioinput", false).then(setMicrophones);
    Room.getLocalDevices("videoinput", false).then(setCameras);

    return () => {
      // 참여하면 트랙 소유권이 Room으로 넘어가므로 그때는 정리하지 않는다
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
    const element = previewRef.current;
    if (!camTrack || !element) return;

    camTrack.attach(element);
    return () => {
      camTrack.detach(element);
    };
  }, [camTrack]);

  const toggleMic = async () => {
    // 이미 잡아둔 트랙이 있으면 mute로만 껐다 켠다 (기기를 새로 잡지 않는다)
    if (micTrack) {
      const next = !micOn;
      if (next) await micTrack.unmute();
      else await micTrack.mute();
      setMicOn(next);
      return;
    }

    try {
      const [audio] = await createLocalTracks({
        audio: microphoneId ? { deviceId: microphoneId } : true,
      });
      const track = audio as LocalAudioTrack;

      tracksRef.current.push(track);
      setMicTrack(track);
      setMicrophoneId(track.mediaStreamTrack.getSettings().deviceId ?? "");
      setMicOn(true);
      setError("");
      // 권한을 받은 뒤에 다시 조회해야 기기 이름(label)이 채워진다
      await loadDevices();
    } catch {
      setError("마이크 권한을 허용해 주세요.");
    }
  };

  const toggleCam = async () => {
    if (camTrack) {
      const next = !camOn;
      if (next) await camTrack.unmute();
      else await camTrack.mute();
      setCamOn(next);
      return;
    }

    try {
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
    }
  };

  // 아직 트랙을 잡지 않았으면 선택만 기억해 두고, 켤 때 그 기기로 잡는다
  const changeMicrophone = async (deviceId: string) => {
    setMicrophoneId(deviceId);
    if (micTrack) await micTrack.restartTrack({ deviceId });
  };

  const changeCamera = async (deviceId: string) => {
    setCameraId(deviceId);
    if (camTrack) await camTrack.restartTrack({ deviceId });
  };

  const submit = async () => {
    if (joining) return;

    setJoining(true);
    setError("");
    startConnecting(projectId);

    try {
      const info = await join(projectId);
      handedOffRef.current = true;

      // 끈 상태로 들어가는 트랙은 넘기지 않고 정리한다
      // (회의 중 버튼을 누르면 Room이 선택된 기기로 새로 잡는다)
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
