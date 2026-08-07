package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects/{projectId}/nodes")
public class GraphNodeCommandController {

    private final GraphNodeUpdateService updateService;

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
}
