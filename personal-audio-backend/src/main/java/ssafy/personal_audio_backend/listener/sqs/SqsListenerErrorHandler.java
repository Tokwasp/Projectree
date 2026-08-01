package ssafy.personal_audio_backend.listener.sqs;

import io.awspring.cloud.sqs.listener.errorhandler.ErrorHandler;
import java.util.Collection;
import lombok.extern.slf4j.Slf4j;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

/**
 * 리스너 예외를 한 곳에서 로깅한다.
 * 여기서 예외를 삼키면 실패한 메시지가 삭제되므로 반드시 다시 던진다.
 */
@Slf4j
@Component
public class SqsListenerErrorHandler implements ErrorHandler<Object> {

    @Override
    public void handle(Message<Object> message, Throwable throwable) {
        log.error("sqs message processing failed. payload={}", message.getPayload(), throwable);
        throw toRuntimeException(throwable);
    }

    @Override
    public void handle(Collection<Message<Object>> messages, Throwable throwable) {
        log.error("sqs batch processing failed. size={}", messages.size(), throwable);
        throw toRuntimeException(throwable);
    }

    private RuntimeException toRuntimeException(Throwable throwable) {
        if (throwable instanceof RuntimeException runtimeException) {
            return runtimeException;
        }
        return new IllegalStateException(throwable);
    }
}
