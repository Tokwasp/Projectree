package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteStatusResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class GraphNodeDeleteStatusService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final NodeDeleteCommandRepository commandRepository;
    private final NodeDeleteCommandItemRepository itemRepository;

    @Transactional(readOnly = true)
    public GraphNodeDeleteStatusResponse getStatus(
            int projectId,
            UUID commandId,
            int memberId
    ) {
        validateProjectAccess(projectId, memberId);

        String commandIdValue = commandId.toString();
        NodeDeleteCommand command = commandRepository
                .findByProjectIdAndCommandId(projectId, commandIdValue)
                .orElseThrow(() -> new CustomException(
                        GraphNodeDeleteErrorCode.NODE_DELETE_COMMAND_NOT_FOUND
                ));
        List<String> requestedNodeIds =
                itemRepository.findRequestedNodeIdsByCommandId(commandIdValue);

        return new GraphNodeDeleteStatusResponse(
                commandId,
                command.getProjectId(),
                List.copyOf(requestedNodeIds),
                command.getExpectedGraphVersion(),
                command.getResultGraphVersion(),
                command.getStatus(),
                command.getReasonCode(),
                command.getRequestedAt(),
                command.getCompletedAt()
        );
    }

    private void validateProjectAccess(int projectId, int memberId) {
        if (!projectRepository.existsById(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }
    }
}
