package ssafy.personal_audio_backend.global.listener.sqs;

import io.awspring.cloud.sqs.listener.errorhandler.ErrorHandler;
import java.util.Collection;
import lombok.extern.slf4j.Slf4j;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class SqsListenerErrorHandler implements ErrorHandler<Object> {

    @Override
    public void handle(Message<Object> message, Throwable throwable) {
        log.error("sqs message processing failed. payload={}, cause={}",
                message.getPayload(), rootCauseOf(throwable));
        throw toRuntimeException(throwable);
    }

    @Override
    public void handle(Collection<Message<Object>> messages, Throwable throwable) {
        log.error("sqs batch processing failed. size={}, cause={}",
                messages.size(), rootCauseOf(throwable));
        throw toRuntimeException(throwable);
    }

    private RuntimeException toRuntimeException(Throwable throwable) {
        if (throwable instanceof RuntimeException runtimeException) {
            return runtimeException;
        }
        return new IllegalStateException(throwable);
    }

    private String rootCauseOf(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current.toString();
    }
}
