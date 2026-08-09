package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

@Component
@RequiredArgsConstructor
public class GraphProjectionReplacer {

    private final NodeEvidenceProjectionRepository evidenceRepository;
    private final ProjectNodeProjectionRepository nodeRepository;

    @Transactional(propagation = Propagation.MANDATORY)
    public void replace(int projectId, ProjectGraphSnapshot snapshot, Instant syncedAt) {
        evidenceRepository.deleteAllByProjectId(projectId);
        nodeRepository.deleteAllByProjectId(projectId);

        nodeRepository.saveAllAndFlush(snapshot.nodes().stream()
                .map(node -> ProjectNodeProjection.from(projectId, node, syncedAt))
                .toList());
        evidenceRepository.saveAllAndFlush(snapshot.evidences().stream()
                .map(evidence -> NodeEvidenceProjection.from(evidence, syncedAt))
                .toList());
    }
}
