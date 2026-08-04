package com.ssafy.projectree.domain.meeting.result.event;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
@RequiredArgsConstructor
public class AnalysisResultEventParser {

    private final ObjectMapper objectMapper;

    public AnalysisResultEventEnvelope parse(String messageBody) {
        if (messageBody == null || messageBody.isBlank()) {
            throw new AnalysisResultContractException("Analysis result message body must not be blank");
        }
        try {
            return objectMapper.readValue(messageBody, AnalysisResultEventEnvelope.class);
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException("Analysis result event JSON is invalid", exception);
        }
    }
}
