package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphMergedSourcesResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeDetailResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodePageResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeResponse;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "project_graph")
@Validated
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects/{projectId}")
public class GraphQueryController {

    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 50;

    private final GraphQueryService graphQueryService;

    @Operation(summary = "프로젝트 ACTIVE Graph Tree 조회")
    @GetMapping("/nodes/tree")
    public ResponseEntity<ApiResponse<GraphTreeResponse>> getTree(
            @PathVariable int projectId,
            @Login LoginMember loginMember
    ) {
        return ResponseEntity.ok(ApiResponse.success(
                graphQueryService.getTree(projectId, loginMember.getId())
        ));
    }

    @Operation(summary = "프로젝트 UNATTACHED Graph Node 목록 조회")
    @GetMapping("/nodes")
    public ResponseEntity<ApiResponse<GraphNodePageResponse>> getUnattachedNodes(
            @PathVariable int projectId,
            @RequestParam(required = false) String graphState,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(MAX_PAGE_SIZE) int size,
            @Login LoginMember loginMember
    ) {
        return ResponseEntity.ok(ApiResponse.success(graphQueryService.getUnattachedNodes(
                projectId,
                loginMember.getId(),
                graphState,
                page,
                size
        )));
    }

    @Operation(summary = "Graph Node 상세 및 Evidence 조회")
    @GetMapping("/nodes/{nodeId}")
    public ResponseEntity<ApiResponse<GraphNodeDetailResponse>> getNodeDetail(
            @PathVariable int projectId,
            @PathVariable String nodeId,
            @Login LoginMember loginMember
    ) {
        return ResponseEntity.ok(ApiResponse.success(
                graphQueryService.getNodeDetail(projectId, nodeId, loginMember.getId())
        ));
    }

    @Operation(summary = "ACTIVE 대표 Node의 MERGED Source 조회")
    @GetMapping("/nodes/{nodeId}/merged-sources")
    public ResponseEntity<ApiResponse<GraphMergedSourcesResponse>> getMergedSources(
            @PathVariable int projectId,
            @PathVariable String nodeId,
            @Login LoginMember loginMember
    ) {
        return ResponseEntity.ok(ApiResponse.success(
                graphQueryService.getMergedSources(projectId, nodeId, loginMember.getId())
        ));
    }

    @Operation(summary = "Meeting에서 생성된 Graph Node 목록 조회")
    @GetMapping("/meetings/{meetingId}/nodes")
    public ResponseEntity<ApiResponse<GraphNodePageResponse>> getMeetingNodes(
            @PathVariable int projectId,
            @PathVariable int meetingId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(MAX_PAGE_SIZE) int size,
            @Login LoginMember loginMember
    ) {
        return ResponseEntity.ok(ApiResponse.success(graphQueryService.getMeetingNodes(
                projectId,
                meetingId,
                loginMember.getId(),
                page,
                size
        )));
    }
}
