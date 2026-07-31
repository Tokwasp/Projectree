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

  // ref로 element를 들고 있으면 effect가 element 등장 시점을 놓칠 수 있다 — state로 받는다
  const [previewEl, setPreviewEl] = useState<HTMLVideoElement | null>(null);
  const previewRef = useCallback((element: HTMLVideoElement | null) => {
    setPreviewEl(element);
  }, []);

  const tracksRef = useRef<LocalTrack[]>([]);
  const handedOffRef = useRef(false);
  // state는 비동기라 연타를 막지 못한다 — 동기 가드는 ref로 둔다
  const camPendingRef = useRef(false);
  const micPendingRef = useRef(false);

  const micLevel = useMicLevel(micTrack, micOn);

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

  // camOn까지 의존해야 mute(트랙 stop) → unmute(기기 재획득) 후 다시 attach된다
  useEffect(() => {
    if (!camTrack || !previewEl || !camOn) return;

    camTrack.attach(previewEl);
    return () => {
      camTrack.detach(previewEl);
    };
  }, [camTrack, previewEl, camOn]);

  // 기기 획득은 권한 프롬프트까지 끼면 수 초가 걸린다 — 그 사이 연타하면 같은 기기에
  // getUserMedia가 두 번 나가고, 앞 트랙이 고아가 되어 카메라를 계속 점유한다
  const toggleMic = async () => {
    if (micPendingRef.current) return;
    micPendingRef.current = true;
    setMicBusy(true);

    try {
      // 이미 잡아둔 트랙이 있으면 mute로만 껐다 켠다 (기기를 새로 잡지 않는다)
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
      // 권한을 받은 뒤에 다시 조회해야 기기 이름(label)이 채워진다
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

  // restartTrack은 트랙이 꺼져 있어도 즉시 기기를 다시 잡아 카메라·마이크를 켜버린다.
  // setDeviceId는 muted면 pendingDeviceChange로 미뤄뒀다가 unmute 때 반영하므로
  // "꺼둔 채 기기만 바꾸기"가 정상 동작한다.
  // deviceId를 문자열로 넘기면 ideal 제약이라 브라우저가 다른 기기를 줄 수 있어 exact로 넘긴다.
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

    // 언마운트 정리가 tracksRef를 비우므로 미리 붙잡아 둔다
    const acquired = tracksRef.current;

    try {
      // 토큰을 먼저 받는다 — 실패해도 모달이 살아 있어야 에러를 보여줄 수 있다
      // 테스트용: projectId/memberId/memberName은 meetingApi에 하드코딩되어 있다
      // const info = await join(projectId);
      const info = await join();

      // startConnecting이 phase를 "connecting"으로 바꾸는 순간 ProjectMeeting이
      // 이 모달을 언마운트한다. 그 전에 인계 표시를 해두지 않으면 언마운트 정리가
      // 트랙을 stop해버려, 이미 끝난(ended) 트랙이 회의에 올라가고 화면이 검게 나온다
      handedOffRef.current = true;
      startConnecting(projectId);

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
      // 인계 표시 후 실패했다면 이미 언마운트라 정리가 돌지 않는다 — 여기서 직접 끈다
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
