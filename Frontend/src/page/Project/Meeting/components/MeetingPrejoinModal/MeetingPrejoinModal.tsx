import style from "./MeetingPrejoinModal.module.css";
import { useMeetingPrejoin } from "../../hooks/useMeetingPrejoin";
import { MIC_LEVEL_SEGMENTS } from "../../hooks/useMicLevel";
import {
  CamOffIcon,
  CamOnIcon,
  MicOffIcon,
  MicOnIcon,
} from "./PrejoinIcons";

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
  } = useMeetingPrejoin(projectId);

  return (
    <div className={style.backdrop}>
      <section className={style.modal} aria-labelledby="prejoinTitle">
        <div className={style.header}>
          <div className={style.titleDiv}>
            <span className={style.title} id="prejoinTitle">
              회의 참여
            </span>
            <span className={style.description}>
              카메라와 마이크를 확인한 뒤 참여하세요.
            </span>
          </div>
          <p className={style.recordNotice}>이 회의는 음성이 녹음됩니다.</p>
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
              <div className={style.previewControls}>
                <button
                  className={micOn ? style.toggleOn : style.toggleOff}
                  type="button"
                  onClick={toggleMic}
                  disabled={micBusy}
                  aria-pressed={micOn}
                  aria-label={micOn ? "마이크 끄기" : "마이크 켜기"}
                  title={micOn ? "마이크 켜짐" : "마이크 꺼짐"}
                >
                  {micOn ? <MicOnIcon /> : <MicOffIcon />}
                </button>
                <button
                  className={camOn ? style.toggleOn : style.toggleOff}
                  type="button"
                  onClick={toggleCam}
                  disabled={camBusy}
                  aria-pressed={camOn}
                  aria-label={camOn ? "카메라 끄기" : "카메라 켜기"}
                  title={camOn ? "카메라 켜짐" : "카메라 꺼짐"}
                >
                  {camOn ? <CamOnIcon /> : <CamOffIcon />}
                </button>
              </div>
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

            <div className={style.meter}>
              <span className={style.meterLabel}>마이크 입력</span>
              <div
                className={style.meterBars}
                role="meter"
                aria-label="마이크 입력 레벨"
                aria-valuemin={0}
                aria-valuemax={MIC_LEVEL_SEGMENTS}
                aria-valuenow={micLevel}
              >
                {Array.from({ length: MIC_LEVEL_SEGMENTS }, (_, index) => (
                  <span
                    key={index}
                    className={
                      index < micLevel ? style.meterBarOn : style.meterBar
                    }
                  />
                ))}
              </div>
              <span className={style.meterHint}>
                {micOn
                  ? "말해 보세요. 막대가 움직이면 정상입니다."
                  : "마이크를 켜면 입력이 표시됩니다."}
              </span>
            </div>
          </div>
        </div>
        <div className={style.actions}>
          <p className={style.error} role="alert">
            {error}
          </p>
          <div className={style.actionButtons}>
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
      </section>
    </div>
  );
}
