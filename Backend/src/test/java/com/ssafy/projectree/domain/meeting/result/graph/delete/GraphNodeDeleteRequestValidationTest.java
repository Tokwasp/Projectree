package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteRequest;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class GraphNodeDeleteRequestValidationTest extends IntegrationTestSupport {

    private static final String NODE_ID = "0afdda91-2576-54d3-bb87-8e9263b1d17c";

    @Autowired
    private Validator validator;

    @Test
    void acceptsCanonicalUuidListAndZeroGraphVersion() {
        assertThat(violations(new GraphNodeDeleteRequest(List.of(NODE_ID), 0))).isZero();
    }

    @Test
    void acceptsGraphVersionAboveIntegerRangeWithoutLoss() {
        long largeVersion = (long) Integer.MAX_VALUE + 10L;
        GraphNodeDeleteRequest request = new GraphNodeDeleteRequest(List.of(NODE_ID), largeVersion);

        assertThat(violations(request)).isZero();
        assertThat(request.expectedGraphVersion()).isEqualTo(largeVersion);
    }

    @Test
    void rejectsNullAndEmptyNodeIds() {
        assertThat(violations(new GraphNodeDeleteRequest(null, 0))).isPositive();
        assertThat(violations(new GraphNodeDeleteRequest(List.of(), 0))).isPositive();
    }

    @Test
    void acceptsOneThousandNodeIdsAndRejectsOneThousandOne() {
        assertThat(violations(new GraphNodeDeleteRequest(
                Collections.nCopies(1000, NODE_ID),
                0
        ))).isZero();
        assertThat(violations(new GraphNodeDeleteRequest(
                Collections.nCopies(1001, NODE_ID),
                0
        ))).isPositive();
    }

    @Test
    void rejectsNullBlankAndNonUuidItems() {
        List<String> withNull = new ArrayList<>();
        withNull.add(null);
        assertThat(violations(new GraphNodeDeleteRequest(withNull, 0))).isPositive();
        assertThat(violations(new GraphNodeDeleteRequest(List.of(" "), 0))).isPositive();
        assertThat(violations(new GraphNodeDeleteRequest(List.of("not-a-uuid"), 0))).isPositive();
    }

    @Test
    void rejectsNonCanonicalUuidAndNegativeGraphVersion() {
        assertThat(violations(new GraphNodeDeleteRequest(
                List.of(NODE_ID.toUpperCase()),
                0
        ))).isPositive();
        assertThat(violations(new GraphNodeDeleteRequest(
                List.of(UUID.randomUUID().toString()),
                -1
        ))).isPositive();
    }

    private int violations(GraphNodeDeleteRequest request) {
        return validator.validate(request).size();
    }
}
