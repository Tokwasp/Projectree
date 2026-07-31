import {
  Room,
  RoomEvent,
  Track,
  type LocalAudioTrack,
  type LocalTrackPublication,
  type LocalVideoTrack,
  type Participant,
  type RemoteTrack,
} from "livekit-client";
import { useMeetingStore } from "../store/meetingStore";
import type { MeetingParticipant, MeetingTileKind } from "../store/meetingStore";
import type { JoinResponse } from "../page/Project/Meeting/api/meetingApi";

export const LOCAL_CAMERA_TILE = "local-camera";
export const LOCAL_SCREEN_TILE = "local-screen";

interface ConnectOptions {
  info: JoinResponse;
  micTrack: LocalAudioTrack | null;
  camTrack: LocalVideoTrack | null;
  micDeviceId?: string;
  camDeviceId?: string;
}

// 라우트가 바뀌어도 세션이 살아 있어야 하므로 컴포넌트 밖에 둔다
let room: Room | null = null;

// 트랙은 스토어에 넣지 않는다(리렌더 유발) — id로만 꺼낸다
const videoTracks = new Map<string, Track>();

const store = () => useMeetingStore.getState();

export const getVideoTrack = (id: string) => videoTracks.get(id);

interface TileOptions {
  kind: MeetingTileKind;
  identity: string;
  mirrored?: boolean;
}

const addTile = (
  id: string,
  label: string,
  track: Track,
  { kind, identity, mirrored = false }: TileOptions,
) => {
  videoTracks.set(id, track);
  store().addVideoTile({ id, label, mirrored, kind, identity });
};

const removeTile = (id: string) => {
  videoTracks.delete(id);
  store().removeVideoTile(id);
};

const toParticipant = (
  participant: Participant,
  isLocal: boolean,
): MeetingParticipant => {
  const micPublication = participant.getTrackPublication(
    Track.Source.Microphone,
  );
  const camPublication = participant.getTrackPublication(Track.Source.Camera);

  return {
    identity: participant.identity,
    name: participant.name || participant.identity,
    isLocal,
    micOn: micPublication ? !micPublication.isMuted : false,
    camOn: camPublication ? !camPublication.isMuted : false,
  };
};

const syncParticipants = (current: Room) => {
  store().setParticipants([
    toParticipant(current.localParticipant, true),
    ...[...current.remoteParticipants.values()].map((participant) =>
      toParticipant(participant, false),
    ),
  ]);
};

// 원격 오디오는 DOM에 붙여야 실제로 소리가 난다. 구독이 오버레이 마운트보다
// 먼저 일어날 수 있어, 항상 존재하는 document.body에 숨겨서 붙인다
const attachRemoteAudio = (track: RemoteTrack, id: string) => {
  if (document.querySelector(`audio[data-meeting-audio="${id}"]`)) return;

  const element = track.attach() as HTMLAudioElement;
  element.dataset.meetingAudio = id;
  element.autoplay = true;
  element.style.display = "none";
  document.body.appendChild(element);
};

const removeRemoteAudio = (id: string) => {
  document.querySelector(`audio[data-meeting-audio="${id}"]`)?.remove();
};

const teardown = () => {
  room = null;
  videoTracks.clear();
  document
    .querySelectorAll("audio[data-meeting-audio]")
    .forEach((element) => element.remove());
  store().reset();
};

const wireEvents = (current: Room) => {
  const resync = () => syncParticipants(current);

  current
    .on(
      RoomEvent.TrackSubscribed,
      (track: RemoteTrack, publication, participant: Participant) => {
        const id = `${participant.identity}-${track.sid}`;
        const name = participant.name || participant.identity;

        if (track.kind === Track.Kind.Video) {
          // source를 봐야 상대의 화면공유를 스포트라이트로 띄울 수 있다
          const isScreen = publication.source === Track.Source.ScreenShare;

          addTile(id, isScreen ? `${name}의 화면` : name, track, {
            kind: isScreen ? "screen" : "camera",
            identity: participant.identity,
          });
        } else if (track.kind === Track.Kind.Audio) {
          attachRemoteAudio(track, id);
        }
        resync();
      },
    )
    .on(
      RoomEvent.TrackUnsubscribed,
      (track: RemoteTrack, _publication, participant: Participant) => {
        const id = `${participant.identity}-${track.sid}`;

        removeTile(id);
        removeRemoteAudio(id);
        track.detach().forEach((element) => element.remove());
        resync();
      },
    )
    .on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) =>
      store().setSpeakers(speakers.map((participant) => participant.identity)),
    )
    // 브라우저 기본 UI의 "공유 중지"로 끝나는 경우도 상태를 맞춰야 한다
    .on(
      RoomEvent.LocalTrackUnpublished,
      (publication: LocalTrackPublication) => {
        if (publication.source === Track.Source.ScreenShare) {
          removeTile(LOCAL_SCREEN_TILE);
          store().setDevices({ screenOn: false });
        }
        resync();
      },
    )
    .on(RoomEvent.TrackMuted, resync)
    .on(RoomEvent.TrackUnmuted, resync)
    .on(RoomEvent.ParticipantConnected, resync)
    .on(RoomEvent.ParticipantDisconnected, resync)
    // 자동재생이 막히면 canPlaybackAudio가 false가 된다 → 배너로 클릭 유도
    .on(RoomEvent.AudioPlaybackStatusChanged, () =>
      store().setNeedSound(!current.canPlaybackAudio),
    )
    // 서버가 방을 닫거나 네트워크가 끊긴 경우
    .on(RoomEvent.Disconnected, () => {
      if (room === current) teardown();
    });
};

export const connectMeeting = async ({
  info,
  micTrack,
  camTrack,
  micDeviceId,
  camDeviceId,
}: ConnectOptions) => {
  // adaptiveStream/dynacast는 "보이는 요소만 구독·송출"이라, 소규모 회의에서
  // 늦게 들어온 참가자가 상대 카메라를 못 보는 문제를 만든다 → 끈다
  // 기기 기본값은 회의 중 토글로 새로 잡을 때 쓰인다
  const current = new Room({
    adaptiveStream: false,
    dynacast: false,
    audioCaptureDefaults: micDeviceId ? { deviceId: micDeviceId } : undefined,
    videoCaptureDefaults: camDeviceId ? { deviceId: camDeviceId } : undefined,
  });

  room = current;
  wireEvents(current);
  await current.connect(info.livekitUrl, info.token);

  // 프리조인에서 켜둔 트랙만 그대로 송출한다
  // (setMicrophoneEnabled를 쓰면 기기를 새로 잡아 이중 점유가 된다)
  if (micTrack) await current.localParticipant.publishTrack(micTrack);

  if (camTrack) {
    await current.localParticipant.publishTrack(camTrack);
    addTile(LOCAL_CAMERA_TILE, "나", camTrack, {
      kind: "camera",
      identity: current.localParticipant.identity,
      mirrored: true,
    });
  }

  // connect의 await 때문에 사용자 활성화가 만료될 수 있다 → 실패하면 배너로 유도
  await current.startAudio().catch(() => undefined);
  store().setNeedSound(!current.canPlaybackAudio);

  store().markLive(info.roomName, {
    micOn: micTrack !== null,
    camOn: camTrack !== null,
    screenOn: false,
  });
  syncParticipants(current);
};

export const disconnectMeeting = async () => {
  const current = room;
  room = null;

  if (current) await current.disconnect();
  teardown();
};

export const toggleMicrophone = async () => {
  const current = room;
  if (!current) return;

  const next = !store().micOn;
  await current.localParticipant.setMicrophoneEnabled(next);
  store().setDevices({ micOn: next });
  syncParticipants(current);
};

export const toggleCamera = async () => {
  const current = room;
  if (!current) return;

  const next = !store().camOn;
  await current.localParticipant.setCameraEnabled(next);
  store().setDevices({ camOn: next });

  // 첫 켜기는 publish라 TrackMuted/Unmuted가 뜨지 않는다 —
  // 여기서 직접 맞추지 않으면 participants의 camOn이 false로 남아 내 타일이 안 보인다
  syncParticipants(current);

  if (!next) {
    removeTile(LOCAL_CAMERA_TILE);
    return;
  }

  const publication = current.localParticipant.getTrackPublication(
    Track.Source.Camera,
  );
  if (publication?.track) {
    addTile(LOCAL_CAMERA_TILE, "나", publication.track, {
      kind: "camera",
      identity: current.localParticipant.identity,
      mirrored: true,
    });
  }
};

export const toggleScreenShare = async () => {
  const current = room;
  if (!current) return;

  const next = !store().screenOn;
  await current.localParticipant.setScreenShareEnabled(next);
  store().setDevices({ screenOn: next });
  syncParticipants(current);

  if (!next) {
    removeTile(LOCAL_SCREEN_TILE);
    return;
  }

  const publication = current.localParticipant.getTrackPublication(
    Track.Source.ScreenShare,
  );
  if (publication?.track) {
    addTile(LOCAL_SCREEN_TILE, "내 화면", publication.track, {
      kind: "screen",
      identity: current.localParticipant.identity,
    });
  }
};

// 반드시 사용자 클릭 핸들러 안에서 호출해야 자동재생 차단이 풀린다
export const enableSound = async () => {
  const current = room;
  if (!current) return;

  await current.startAudio();
  store().setNeedSound(!current.canPlaybackAudio);
};
