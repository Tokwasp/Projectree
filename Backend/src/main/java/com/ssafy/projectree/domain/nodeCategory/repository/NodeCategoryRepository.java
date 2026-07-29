package com.ssafy.projectree.domain.nodeCategory.repository;


import com.ssafy.projectree.domain.nodeCategory.entity.NodeCategory;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NodeCategoryRepository extends JpaRepository<NodeCategory, Integer> {
}
