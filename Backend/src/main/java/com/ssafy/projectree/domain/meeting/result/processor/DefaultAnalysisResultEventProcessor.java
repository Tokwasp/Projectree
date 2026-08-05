package com.ssafy.projectree.domain.meeting.result.processor;

import com.ssafy.projectree.domain.meeting.result.dispatcher.AnalysisResultEventDispatcher;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.DuplicateAnalysisResultEventException;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.meeting.result.validation.AnalysisEventReferenceValidator;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class DefaultAnalysisResultEventProcessor implements AnalysisResultEventProcessor {

    private final ResultInboxService resultInboxService;
    private final AnalysisEventReferenceValidator referenceValidator;
    private final AnalysisResultEventDispatcher dispatcher;

    @Override
    public AnalysisResultProcessingOutcome process(AnalysisResultEventEnvelope event) {
        if (resultInboxService.isProcessed(event.eventId())) {
            return AnalysisResultProcessingOutcome.DUPLICATE;
        }
        try {
            referenceValidator.validateReferences(event);
            dispatcher.dispatch(event);
            return AnalysisResultProcessingOutcome.PROCESSED;
        } catch (DuplicateAnalysisResultEventException exception) {
            return AnalysisResultProcessingOutcome.DUPLICATE;
        }
    }
}
