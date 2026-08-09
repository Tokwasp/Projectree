package com.ssafy.projectree.domain.nodeCategory.controller;

import com.ssafy.projectree.domain.nodeCategory.dto.response.NodeCategoryResponseDto;
import com.ssafy.projectree.domain.nodeCategory.service.NodeCategoryService;
import com.ssafy.projectree.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(name = "node_category")
@RestController
@RequestMapping("/api/categories")
@RequiredArgsConstructor
public class NodeCategoryController {

    private final NodeCategoryService nodeCategoryService;

    @GetMapping
    public ResponseEntity<ApiResponse<List<NodeCategoryResponseDto>>> getCategories() {
        return ResponseEntity.ok(ApiResponse.success(nodeCategoryService.getCategories()));
    }

}
