package com.ssafy.projectree.domain.nodeCategory.service;

import com.ssafy.projectree.domain.nodeCategory.dto.response.NodeCategoryResponseDto;
import com.ssafy.projectree.domain.nodeCategory.repository.NodeCategoryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NodeCategoryService {

    private final NodeCategoryRepository nodeCategoryRepository;

    public List<NodeCategoryResponseDto> getCategories() {
        return nodeCategoryRepository
                .findAll(Sort.by(Sort.Direction.ASC, "id"))
                .stream()
                .map(NodeCategoryResponseDto::new)
                .toList();
    }
}
