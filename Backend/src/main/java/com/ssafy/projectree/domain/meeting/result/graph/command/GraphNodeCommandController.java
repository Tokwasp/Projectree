package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.delete.GraphNodeDeleteService;
import com.ssafy.projectree.domain.meeting.result.graph.delete.GraphNodeDeleteStatusService;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteRequest;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteStatusResponse;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects/{projectId}/nodes")
public class GraphNodeCommandController {

    private final GraphNodeUpdateService updateService;
    private final GraphNodeDeleteService deleteService;
    private final GraphNodeDeleteStatusService deleteStatusService;

    @PatchMapping("/{nodeId}")
    public ResponseEntity<ApiResponse<NodeContentUpdateAcceptedResponse>> update(
            @PathVariable int projectId,
            @PathVariable String nodeId,
            @Valid @RequestBody NodeContentUpdateRequest request,
            @Login LoginMember loginMember
    ) {
        NodeContentUpdateAcceptedResponse response = updateService.update(
                projectId,
                nodeId,
                loginMember.getId(),
                request
        );
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(ApiResponse.accepted(response));
    }

    @PostMapping("/delete")
    public ResponseEntity<ApiResponse<GraphNodeDeleteAcceptedResponse>> delete(
            @PathVariable int projectId,
            @Valid @RequestBody GraphNodeDeleteRequest request,
            @Login LoginMember loginMember
    ) {
        GraphNodeDeleteAcceptedResponse response = deleteService.deleteNodes(
                projectId,
                loginMember.getId(),
                request
        );
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(ApiResponse.accepted(response));
    }

    @GetMapping("/delete-commands/{commandId}")
    public ResponseEntity<ApiResponse<GraphNodeDeleteStatusResponse>> getDeleteStatus(
            @PathVariable int projectId,
            @PathVariable UUID commandId,
            @Login LoginMember loginMember
    ) {
        GraphNodeDeleteStatusResponse response = deleteStatusService.getStatus(
                projectId,
                commandId,
                loginMember.getId()
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
