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

let room: Room | null = null;

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
    .on(RoomEvent.AudioPlaybackStatusChanged, () =>
      store().setNeedSound(!current.canPlaybackAudio),
    )
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
  const current = new Room({
    adaptiveStream: false,
    dynacast: false,
    audioCaptureDefaults: micDeviceId ? { deviceId: micDeviceId } : undefined,
    videoCaptureDefaults: camDeviceId ? { deviceId: camDeviceId } : undefined,
  });

  room = current;
  wireEvents(current);
  await current.connect(info.livekitUrl, info.token);

  if (micTrack) await current.localParticipant.publishTrack(micTrack);

  if (camTrack) {
    await current.localParticipant.publishTrack(camTrack);
    addTile(LOCAL_CAMERA_TILE, "나", camTrack, {
      kind: "camera",
      identity: current.localParticipant.identity,
      mirrored: true,
    });
  }

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

export const enableSound = async () => {
  const current = room;
  if (!current) return;

  await current.startAudio();
  store().setNeedSound(!current.canPlaybackAudio);
};
