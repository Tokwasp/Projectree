import style from "./MeetingPrejoinModal.module.css";
import { useMeetingPrejoin } from "../../hooks/useMeetingPrejoin";

interface MeetingPrejoinModalProps {
  projectId: number;
}

export default function MeetingPrejoinModal({
  projectId,
}: MeetingPrejoinModalProps) {
  const {
    cameras,
    microphones,
    cameraId,
    microphoneId,
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
  } = useMeetingPrejoin(projectId);

  return (
    <div className={style.backdrop}>
      <section className={style.modal} aria-labelledby="prejoinTitle">
        <div className={style.titleDiv}>
          <span className={style.title} id="prejoinTitle">
            회의 참여
          </span>
          <span className={style.description}>
            카메라와 마이크를 확인한 뒤 참여하세요.
          </span>
        </div>
        <div className={style.contentDiv}>
          <div className={style.leftSection}>
            <div className={style.preview}>
              <video
                className={camOn ? style.previewVideo : style.previewOff}
                ref={previewRef}
                autoPlay
                muted
                playsInline
              />
              {!camOn && (
                <span className={style.previewNotice}>
                  카메라가 꺼져 있습니다
                </span>
              )}
            </div>
          </div>
          <div className={style.rightSection}>
            <div className={style.devices}>
              <label className={style.field}>
                마이크
                <select
                  value={microphoneId}
                  onChange={(event) => changeMicrophone(event.target.value)}
                  disabled={microphones.length === 0}
                >
                  {microphones.map((device) => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.label || "기본 마이크"}
                    </option>
                  ))}
                </select>
              </label>

              <label className={style.field}>
                카메라
                <select
                  value={cameraId}
                  onChange={(event) => changeCamera(event.target.value)}
                  disabled={cameras.length === 0}
                >
                  {cameras.map((device) => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.label || "기본 카메라"}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className={style.toggles}>
              <button
                className={micOn ? style.toggleOn : style.toggleOff}
                type="button"
                onClick={toggleMic}
              >
                {micOn ? "마이크 켜짐" : "마이크 꺼짐"}
              </button>
              <button
                className={camOn ? style.toggleOn : style.toggleOff}
                type="button"
                onClick={toggleCam}
              >
                {camOn ? "카메라 켜짐" : "카메라 꺼짐"}
              </button>
            </div>

            <p className={style.recordNotice}>이 회의는 음성이 녹음됩니다.</p>
            <p className={style.error} role="alert">
              {error}
            </p>

            <div className={style.actions}>
              <button className={style.cancel} type="button" onClick={cancel}>
                취소
              </button>
              <button
                className={style.submit}
                type="button"
                onClick={submit}
                disabled={joining}
              >
                {joining ? "연결 중…" : "참여"}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
