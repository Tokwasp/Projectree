package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.UUID;

@Component
public class MeetingSummaryReadyPayloadValidator {

    private static final int MAX_API_PATH_LENGTH = 500;

    public MeetingSummaryReadyPayload validate(
            MeetingSummaryReadyPayload payload,
            AnalysisResultEventEnvelope event
    ) {
        if (payload == null) {
            throw new AnalysisResultContractException("Meeting summary payload must not be null");
        }
        if (payload.summaryVersion() <= 0) {
            throw new AnalysisResultContractException("summaryVersion must be positive");
        }
        if (payload.status() != MeetingSummaryResultStatus.READY) {
            throw new AnalysisResultContractException("Meeting summary status must be READY");
        }
        String apiPath = requireApiPath(payload.apiPath());
        validateApiPath(apiPath, event.meetingId(), payload.summaryVersion());
        return new MeetingSummaryReadyPayload(
                canonicalUuid(payload.meetingSummaryId(), "meetingSummaryId"),
                payload.summaryVersion(),
                payload.status(),
                apiPath
        );
    }

    private String requireApiPath(String apiPath) {
        if (apiPath == null || apiPath.isBlank()) {
            throw new AnalysisResultContractException("apiPath must not be blank");
        }
        if (apiPath.length() > MAX_API_PATH_LENGTH) {
            throw new AnalysisResultContractException("apiPath exceeds maximum length");
        }
        return apiPath;
    }

    private void validateApiPath(String apiPath, int meetingId, int summaryVersion) {
        if (apiPath.startsWith("//")) {
            throw new AnalysisResultContractException("apiPath must not include an authority");
        }
        URI uri;
        try {
            uri = new URI(apiPath);
        } catch (URISyntaxException exception) {
            throw new AnalysisResultContractException("apiPath is not a valid URI", exception);
        }
        if (uri.isAbsolute() || uri.getHost() != null || uri.getAuthority() != null) {
            throw new AnalysisResultContractException("apiPath must be relative");
        }
        if (uri.getFragment() != null) {
            throw new AnalysisResultContractException("apiPath must not contain a fragment");
        }

        String expectedPath = "/api/v1/meetings/" + meetingId + "/summary";
        if (!expectedPath.equals(uri.getPath())) {
            throw new AnalysisResultContractException("apiPath meeting ID does not match event meetingId");
        }
        String query = uri.getRawQuery();
        if (query == null || query.isBlank()) {
            throw new AnalysisResultContractException("apiPath must contain summaryVersion");
        }
        String[] parameters = query.split("&", -1);
        if (parameters.length != 1) {
            throw new AnalysisResultContractException("apiPath must contain exactly one summaryVersion parameter");
        }
        String[] keyValue = parameters[0].split("=", -1);
        if (keyValue.length != 2 || !"summaryVersion".equals(keyValue[0])) {
            throw new AnalysisResultContractException("apiPath must contain summaryVersion parameter");
        }
        try {
            if (Integer.parseInt(keyValue[1]) != summaryVersion) {
                throw new AnalysisResultContractException(
                        "apiPath summaryVersion does not match payload summaryVersion"
                );
            }
        } catch (NumberFormatException exception) {
            throw new AnalysisResultContractException("apiPath summaryVersion must be an integer", exception);
        }
    }

    private String canonicalUuid(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new AnalysisResultContractException(fieldName + " must not be blank");
        }
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equalsIgnoreCase(value)) {
                throw new AnalysisResultContractException(fieldName + " must be a canonical UUID");
            }
            return parsed.toString();
        } catch (IllegalArgumentException exception) {
            throw new AnalysisResultContractException(fieldName + " must be a canonical UUID", exception);
        }
    }
}
