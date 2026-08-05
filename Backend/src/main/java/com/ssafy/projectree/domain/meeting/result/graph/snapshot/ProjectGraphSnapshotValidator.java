package com.ssafy.projectree.domain.meeting.result.graph.snapshot;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Component
public class ProjectGraphSnapshotValidator {

    private static final int SNAPSHOT_SCHEMA_VERSION = 1;

    public ProjectGraphSnapshot validate(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
        if (snapshot == null) {
            throw contract("Graph snapshot must not be null");
        }
        validateSnapshotHeader(event, payload, snapshot);

        Map<String, ProjectGraphSnapshotNode> nodesById = new HashMap<>();
        List<ProjectGraphSnapshotNode> normalizedNodes = new ArrayList<>();
        for (ProjectGraphSnapshotNode node : snapshot.nodes()) {
            ProjectGraphSnapshotNode normalized = normalizeNode(node);
            if (nodesById.putIfAbsent(normalized.nodeId(), normalized) != null) {
                throw contract("Graph snapshot contains duplicate nodeId");
            }
            normalizedNodes.add(normalized);
        }
        validateNodeRelations(nodesById);
        validateParentCycles(nodesById);

        List<ProjectGraphSnapshotEvidence> normalizedEvidences = normalizeAndValidateEvidences(
                snapshot.evidences(), nodesById
        );
        return new ProjectGraphSnapshot(
                snapshot.snapshotSchemaVersion(),
                snapshot.projectId(),
                snapshot.meetingId(),
                canonicalUuid(snapshot.commandId(), "commandId"),
                snapshot.graphVersion(),
                snapshot.generatedAt(),
                List.copyOf(normalizedNodes),
                List.copyOf(normalizedEvidences),
                List.copyOf(snapshot.mergeRecords())
        );
    }

    private void validateSnapshotHeader(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
        if (event == null || payload == null) {
            throw contract("Event and graph payload must not be null");
        }
        if (snapshot.snapshotSchemaVersion() != SNAPSHOT_SCHEMA_VERSION) {
            throw contract("Unsupported graph snapshot schema version");
        }
        if (snapshot.projectId() != requirePositive(event.projectId(), "event projectId")
                || snapshot.meetingId() != requirePositive(event.meetingId(), "event meetingId")) {
            throw contract("Graph snapshot projectId and meetingId must match the event");
        }
        if (!canonicalUuid(snapshot.commandId(), "commandId")
                .equals(canonicalUuid(event.commandId(), "event commandId"))) {
            throw contract("Graph snapshot commandId must match the event");
        }
        if (snapshot.graphVersion() != payload.graphVersion()) {
            throw contract("Graph snapshot graphVersion must match the payload");
        }
        if (snapshot.generatedAt() == null || snapshot.nodes() == null
                || snapshot.evidences() == null || snapshot.mergeRecords() == null) {
            throw contract("Graph snapshot required fields must not be null");
        }
        for (Object mergeRecord : snapshot.mergeRecords()) {
            if (mergeRecord == null || (mergeRecord instanceof tools.jackson.databind.JsonNode node && node.isNull())) {
                throw contract("Graph snapshot mergeRecords must not contain null elements");
            }
        }
    }

    private ProjectGraphSnapshotNode normalizeNode(ProjectGraphSnapshotNode node) {
        if (node == null) {
            throw contract("Graph snapshot node must not be null");
        }
        String nodeId = canonicalUuid(node.nodeId(), "nodeId");
        String parentNodeId = optionalCanonicalUuid(node.parentNodeId(), "parentNodeId");
        String mergedIntoNodeId = optionalCanonicalUuid(node.mergedIntoNodeId(), "mergedIntoNodeId");
        if (node.sourceMeetingId() != null && node.sourceMeetingId() <= 0) {
            throw contract("sourceMeetingId must be positive when present");
        }
        if (node.nodeType() == null || node.category() == null || node.graphState() == null) {
            throw contract("Graph node type, category and state must not be null");
        }
        requireText(node.title(), "node title", 255);
        requireText(node.content(), "node content", Integer.MAX_VALUE);
        if (node.nodeVersion() <= 0 || node.createdAt() == null || node.updatedAt() == null) {
            throw contract("Graph node version and timestamps are required");
        }
        if (node.updatedAt().isBefore(node.createdAt())) {
            throw contract("Graph node updatedAt must not precede createdAt");
        }
        return new ProjectGraphSnapshotNode(
                nodeId, node.sourceMeetingId(), parentNodeId, mergedIntoNodeId,
                node.nodeType(), node.category(), node.graphState(), node.title(), node.content(),
                node.linkSource(), node.nodeVersion(), node.createdAt(), node.updatedAt()
        );
    }

    private void validateNodeRelations(Map<String, ProjectGraphSnapshotNode> nodesById) {
        for (ProjectGraphSnapshotNode node : nodesById.values()) {
            switch (node.graphState()) {
                case ACTIVE -> validateActiveNode(node);
                case UNATTACHED -> {
                    if (node.parentNodeId() != null || node.mergedIntoNodeId() != null) {
                        throw contract("UNATTACHED node cannot have parent or merge target");
                    }
                }
                case MERGED -> validateMergedNode(node, nodesById);
            }
            validateParent(node, nodesById);
        }
    }

    private void validateActiveNode(ProjectGraphSnapshotNode node) {
        if (node.mergedIntoNodeId() != null) {
            throw contract("ACTIVE node cannot have merge target");
        }
        if (node.nodeType() == GraphNodeType.DECISION && node.parentNodeId() != null) {
            throw contract("DECISION node cannot have a parent");
        }
        if ((node.nodeType() == GraphNodeType.ACTION || node.nodeType() == GraphNodeType.ISSUE)
                && node.parentNodeId() == null) {
            throw contract("ACTIVE ACTION and ISSUE nodes require a parent");
        }
    }

    private void validateMergedNode(
            ProjectGraphSnapshotNode node,
            Map<String, ProjectGraphSnapshotNode> nodesById
    ) {
        if (node.parentNodeId() != null || node.mergedIntoNodeId() == null) {
            throw contract("MERGED node requires only a merge target");
        }
        ProjectGraphSnapshotNode target = nodesById.get(node.mergedIntoNodeId());
        if (target == null || target.graphState() != GraphNodeState.ACTIVE
                || target.nodeType() != node.nodeType() || target.category() != node.category()) {
            throw contract("MERGED node target must be an ACTIVE node with matching type and category");
        }
    }

    private void validateParent(ProjectGraphSnapshotNode node, Map<String, ProjectGraphSnapshotNode> nodesById) {
        if (node.parentNodeId() == null) {
            return;
        }
        ProjectGraphSnapshotNode parent = nodesById.get(node.parentNodeId());
        if (parent == null || parent.graphState() != GraphNodeState.ACTIVE || parent.category() != node.category()) {
            throw contract("Graph node parent must be an ACTIVE node in the same category");
        }
        if (node.nodeType() == GraphNodeType.ACTION && parent.nodeType() != GraphNodeType.DECISION) {
            throw contract("ACTION node parent must be a DECISION");
        }
        if (node.nodeType() == GraphNodeType.ISSUE
                && parent.nodeType() != GraphNodeType.DECISION
                && parent.nodeType() != GraphNodeType.ACTION) {
            throw contract("ISSUE node parent must be a DECISION or ACTION");
        }
        if (node.nodeType() == GraphNodeType.DECISION) {
            throw contract("DECISION node cannot have a parent");
        }
    }

    private void validateParentCycles(Map<String, ProjectGraphSnapshotNode> nodesById) {
        Map<String, VisitState> states = new HashMap<>();
        for (String nodeId : nodesById.keySet()) {
            visitParent(nodeId, nodesById, states);
        }
    }

    private void visitParent(
            String nodeId,
            Map<String, ProjectGraphSnapshotNode> nodesById,
            Map<String, VisitState> states
    ) {
        VisitState state = states.get(nodeId);
        if (state == VisitState.VISITING) {
            throw contract("Graph node parent relation contains a cycle");
        }
        if (state == VisitState.DONE) {
            return;
        }
        states.put(nodeId, VisitState.VISITING);
        String parentNodeId = nodesById.get(nodeId).parentNodeId();
        if (parentNodeId != null) {
            visitParent(parentNodeId, nodesById, states);
        }
        states.put(nodeId, VisitState.DONE);
    }

    private List<ProjectGraphSnapshotEvidence> normalizeAndValidateEvidences(
            List<ProjectGraphSnapshotEvidence> evidences,
            Map<String, ProjectGraphSnapshotNode> nodesById
    ) {
        Set<String> evidenceIds = new HashSet<>();
        Map<String, Set<Integer>> ordersByNode = new HashMap<>();
        List<ProjectGraphSnapshotEvidence> normalized = new ArrayList<>();
        for (ProjectGraphSnapshotEvidence evidence : evidences) {
            if (evidence == null) {
                throw contract("Graph evidence must not be null");
            }
            String evidenceId = canonicalUuid(evidence.evidenceId(), "evidenceId");
            String nodeId = canonicalUuid(evidence.nodeId(), "evidence nodeId");
            if (!evidenceIds.add(evidenceId) || !nodesById.containsKey(nodeId)) {
                throw contract("Graph evidenceId must be unique and reference an existing node");
            }
            if (evidence.meetingId() <= 0 || evidence.evidenceOrder() <= 0) {
                throw contract("Graph evidence meetingId and evidenceOrder must be positive");
            }
            requireText(evidence.quoteText(), "evidence quoteText", Integer.MAX_VALUE);
            if (evidence.speakerLabel() != null && evidence.speakerLabel().length() > 100) {
                throw contract("evidence speakerLabel exceeds maximum length");
            }
            if ((evidence.startMs() != null && evidence.startMs() < 0)
                    || (evidence.endMs() != null && evidence.endMs() < 0)
                    || (evidence.startMs() != null && evidence.endMs() != null && evidence.startMs() > evidence.endMs())) {
                throw contract("Graph evidence time range is invalid");
            }
            if (!ordersByNode.computeIfAbsent(nodeId, ignored -> new HashSet<>()).add(evidence.evidenceOrder())) {
                throw contract("Graph evidenceOrder must be unique per node");
            }
            normalized.add(new ProjectGraphSnapshotEvidence(
                    evidenceId, nodeId, evidence.meetingId(), evidence.quoteText(), evidence.speakerLabel(),
                    evidence.startMs(), evidence.endMs(), evidence.evidenceOrder()
            ));
        }
        return normalized;
    }

    private int requirePositive(Integer value, String fieldName) {
        if (value == null || value <= 0) {
            throw contract(fieldName + " must be positive");
        }
        return value;
    }

    private String optionalCanonicalUuid(String value, String fieldName) {
        return value == null ? null : canonicalUuid(value, fieldName);
    }

    private String canonicalUuid(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw contract(fieldName + " must not be blank");
        }
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equalsIgnoreCase(value)) {
                throw contract(fieldName + " must be a canonical UUID");
            }
            return parsed.toString();
        } catch (IllegalArgumentException exception) {
            throw contract(fieldName + " must be a UUID");
        }
    }

    private void requireText(String value, String fieldName, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength) {
            throw contract(fieldName + " is invalid");
        }
    }

    private AnalysisResultContractException contract(String message) {
        return new AnalysisResultContractException(message);
    }

    private enum VisitState {
        VISITING,
        DONE
    }
}
