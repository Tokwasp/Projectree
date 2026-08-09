package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordUpdateRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordUpdateResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional
public class MeetingRecordUpdateService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingRepository meetingRepository;
    private final MeetingRecordRepository meetingRecordRepository;
    private final MeetingRecordContentEncoder contentEncoder;

    public MeetingRecordUpdateResponse update(
            int projectId,
            int meetingId,
            int memberId,
            MeetingRecordUpdateRequest request
    ) {
        requireProjectMember(projectId, memberId);

        Meeting meeting = meetingRepository.findByIdWithProject(meetingId)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_NOT_FOUND));
        if (meeting.getProject().getId() != projectId) {
            throw new CustomException(MeetingErrorCode.MEETING_PROJECT_MISMATCH);
        }
        if (meeting.getCreatorMemberId() == null || meeting.getCreatorMemberId() != memberId) {
            throw new CustomException(
                    MeetingRecordErrorCode.MEETING_RECORD_UPDATE_FORBIDDEN
            );
        }

        MeetingRecord record = meetingRecordRepository.findByMeetingId(meetingId)
                .orElseThrow(() -> new CustomException(
                        MeetingRecordErrorCode.MEETING_RECORD_NOT_FOUND
                ));
        if (record.getVersion() != request.version().longValue()) {
            throw new CustomException(
                    MeetingRecordErrorCode.MEETING_RECORD_VERSION_CONFLICT
            );
        }

        MeetingRecordContentEncoder.EncodedContent content = contentEncoder.encode(
                request.summary(),
                request.decisions(),
                request.nextTodos(),
                request.issues()
        );
        record.update(
                request.title(),
                content.summary(),
                content.decisions(),
                content.nextTodos(),
                content.issues()
        );
        MeetingRecord saved = meetingRecordRepository.saveAndFlush(record);

        return new MeetingRecordUpdateResponse(
                saved.getId(),
                projectId,
                meetingId,
                saved.getTitle(),
                List.copyOf(request.summary()),
                List.copyOf(request.decisions()),
                List.copyOf(request.nextTodos()),
                List.copyOf(request.issues()),
                saved.getVersion(),
                saved.getUpdatedAt()
        );
    }

    private void requireProjectMember(int projectId, int memberId) {
        if (!projectRepository.existsById(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }
    }
}
