package com.ssafy.projectree.domain.nodeCategory.dto.response;

import com.ssafy.projectree.domain.nodeCategory.entity.NodeCategory;
import lombok.Getter;

@Getter
public class NodeCategoryResponseDto {

    private final int id;
    private final String name;

    public NodeCategoryResponseDto(NodeCategory nodeCategory) {
        this.id = nodeCategory.getId();
        this.name = nodeCategory.getCategory().name();
    }

}
