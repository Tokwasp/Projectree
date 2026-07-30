import {
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import style from "./ProjectInvitePopover.module.css";

interface ProjectInvitePopoverProps {
  onClose: () => void;
  onInvite: (emails: string[]) => void;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_INVITE_COUNT = 10;

export default function ProjectInvitePopover({
  onClose,
  onInvite,
}: ProjectInvitePopoverProps) {
  const [email, setEmail] = useState("");
  const [selectedEmails, setSelectedEmails] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");

  const trimmedEmail = email.trim().toLowerCase();
  const isEmailValid = EMAIL_PATTERN.test(trimmedEmail);

  const handleEmailAdd = () => {
    if (!trimmedEmail) {
      return;
    }

    if (!isEmailValid) {
      setErrorMessage("올바른 이메일 주소를 입력해주세요.");
      return;
    }

    if (selectedEmails.includes(trimmedEmail)) {
      setErrorMessage("이미 추가한 이메일입니다.");
      return;
    }

    if (selectedEmails.length >= MAX_INVITE_COUNT) {
      setErrorMessage(
        `한 번에 최대 ${MAX_INVITE_COUNT}명까지 초대할 수 있습니다.`,
      );
      return;
    }

    setSelectedEmails((emails) => [...emails, trimmedEmail]);
    setEmail("");
    setErrorMessage("");
  };

  const handleEmailRemove = (emailToRemove: string) => {
    setSelectedEmails((emails) =>
      emails.filter((selectedEmail) => selectedEmail !== emailToRemove),
    );
    setErrorMessage("");
  };

  const handleKeyDown = (
    event: KeyboardEvent<HTMLInputElement>,
  ) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      handleEmailAdd();
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (selectedEmails.length === 0) {
      return;
    }

    onInvite(selectedEmails);
  };

  return (
    <div
      className={style.popover}
      role="dialog"
      aria-labelledby="project-invite-title"
    >
      <div className={style.header}>
        <div>
          <h2 className={style.title} id="project-invite-title">
            팀원 초대
          </h2>

          <p className={style.description}>
            이메일을 추가해 여러 명을 한 번에 초대할 수 있습니다.
          </p>
        </div>

        <button
          className={style.closeButton}
          type="button"
          aria-label="초대 창 닫기"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <form className={style.form} onSubmit={handleSubmit}>
        <label className={style.label} htmlFor="project-invite-email">
          이메일
        </label>

        {selectedEmails.length > 0 && (
          <div
            className={style.emailList}
            aria-label="초대 대상 이메일"
          >
            {selectedEmails.map((selectedEmail) => (
              <span className={style.emailChip} key={selectedEmail}>
                <span>{selectedEmail}</span>

                <button
                  className={style.emailRemoveButton}
                  type="button"
                  aria-label={`${selectedEmail} 선택 해제`}
                  onClick={() => handleEmailRemove(selectedEmail)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className={style.emailControls}>
          <input
            className={style.input}
            id="project-invite-email"
            type="email"
            value={email}
            placeholder="name@example.com"
            autoComplete="email"
            autoFocus
            onChange={(event) => {
              setEmail(event.target.value);
              setErrorMessage("");
            }}
            onKeyDown={handleKeyDown}
          />

          <button
            className={style.addButton}
            type="button"
            disabled={!trimmedEmail}
            onClick={handleEmailAdd}
          >
            추가
          </button>
        </div>

        <p className={style.helperText}>
          Enter 키로 이메일을 빠르게 추가할 수 있어요.
        </p>

        {errorMessage && (
          <p className={style.errorMessage}>{errorMessage}</p>
        )}

        <button
          className={style.inviteButton}
          type="submit"
          disabled={selectedEmails.length === 0}
        >
          {selectedEmails.length > 0
            ? `${selectedEmails.length}명 초대하기`
            : "초대하기"}
        </button>
      </form>
    </div>
  );
}
