"""Strict quote support with legacy multiline evidence fallback."""
from __future__ import annotations
import re, unicodedata
from dataclasses import asdict, dataclass
from typing import Any

SPEAKER_TIMESTAMP_PATTERN=re.compile(r"^발화자\s+(.+?)\s+\((\d{1,2}:\d{2})\)\s*$")
@dataclass(frozen=True)
class EvidenceSegmentEvaluation:
    segment_index:int; raw_text:str; quote_text:str; speaker_label:str|None; timestamp:str|None
    match_type:str; transcript_start:int|None; transcript_end:int|None; transcript_line_start:int|None; transcript_line_end:int|None
def normalize_quote(text:str)->str:
    text=unicodedata.normalize("NFKC",text).replace("\r\n","\n").replace("\r","\n")
    return "\n".join(" ".join(x.split()) for x in text.splitlines()).strip()
def _lines(transcript:str,start:int,end:int)->tuple[int,int]:
    return transcript.count("\n",0,start)+1, transcript.count("\n",0,max(start,end-1))+1
def find_all_occurrences(transcript:str,quote:str)->list[tuple[int,int]]:
    matches=[]; start=0
    while quote and (index:=transcript.find(quote,start)) >= 0:
        matches.append((index,index+len(quote))); start=index+1
    return matches
def _match(quote:str,transcript:str,previous_end:int|None=None):
    matches=find_all_occurrences(transcript,quote)
    if matches:
        start,end=next((pair for pair in matches if previous_end is not None and pair[0]>=previous_end),matches[0]); a,b=_lines(transcript,start,end); return "EXACT",start,end,a,b,len(matches),len(matches)>1
    nq,nt=normalize_quote(quote),normalize_quote(transcript)
    if nq and nq in nt:return "NORMALIZED_EXACT",None,None,None,None,1,False
    return "UNSUPPORTED",None,None,None,None,0,False
def _blocks(evidence:str):
    """Return text blocks; metadata begins a new block and blank lines end one."""
    result=[]; text=[]; speaker=timestamp=None
    def flush():
        nonlocal text,speaker,timestamp
        if any(x.strip() for x in text): result.append(("\n".join(text).strip(),speaker,timestamp))
        text=[]; speaker=timestamp=None
    for line in evidence.replace("\r\n","\n").replace("\r","\n").splitlines():
        match=SPEAKER_TIMESTAMP_PATTERN.match(line.strip())
        if match:
            flush(); speaker,timestamp=match.group(1),match.group(2); continue
        if not line.strip(): flush(); continue
        text.append(line)
    flush(); return result
def _segments(evidence:str,transcript:str):
    """Try each multiline block first; legacy unseparated unsupported blocks fall back to lines."""
    output=[]
    for block,speaker,timestamp in _blocks(evidence):
        kind,*_= _match(block,transcript)
        if kind!="UNSUPPORTED" or "\n" not in block: output.append((block,block,speaker,timestamp)); continue
        output.extend((line,line,speaker,timestamp) for line in block.splitlines() if line.strip())
    return output
def evaluate_evidence(evidence:str,transcript:str,prediction_index:int)->dict[str,Any]:
    entries=[]
    previous_end=None
    for i,(raw,quote,speaker,timestamp) in enumerate(_segments(evidence,transcript)):
        prior_end=previous_end
        kind,start,end,line_start,line_end,candidates,ambiguous=_match(quote,transcript,prior_end)
        if end is not None: previous_end=end
        if candidates<=1: reason="ONLY_OCCURRENCE" if candidates==1 else None
        elif prior_end is None: reason="FIRST_OCCURRENCE"
        elif start is not None and start>=prior_end: reason="FIRST_AFTER_PREVIOUS_SEGMENT"
        else: reason="FALLBACK_FIRST_OCCURRENCE"
        item=asdict(EvidenceSegmentEvaluation(i,raw,quote,speaker,timestamp,kind,start,end,line_start,line_end)); item.update({"occurrenceCandidateCount":candidates,"occurrenceSelectionAmbiguous":ambiguous,"selectionReason":reason}); entries.append(item)
    count=len(entries); supported=[x for x in entries if x["match_type"]!="UNSUPPORTED"]
    all_supported=count>0 and len(supported)==count
    if not count or not all_supported: contiguous=None
    elif count==1: contiguous=True
    elif any(x["transcript_start"] is None for x in entries): contiguous=None
    else:
        ordered=sorted(entries,key=lambda x:x["transcript_start"])
        # Only whitespace between segments means one continuous source range.
        contiguous=all(not transcript[a["transcript_end"]:b["transcript_start"]].strip() for a,b in zip(ordered,ordered[1:]))
    status="NO_EVIDENCE" if not count else "FULLY_SUPPORTED" if all_supported else "PARTIALLY_SUPPORTED" if supported else "UNSUPPORTED"
    return {"predictionIndex":prediction_index,"hasEvidence":bool(count),"segmentCount":count,"supportedSegmentCount":len(supported),"unsupportedSegmentCount":count-len(supported),"allSegmentsSupported":all_supported,"isContiguous":contiguous,"supportStatus":status,"segments":entries}
def evaluate_case_evidence(nodes:list[dict[str,Any]],transcript:str)->dict[str,Any]:
    details=[evaluate_evidence(str(n.get("evidence")or""),transcript,i) for i,n in enumerate(nodes)]
    segments=sum(x["segmentCount"] for x in details); supported=sum(x["supportedSegmentCount"] for x in details); eligible=[x for x in details if x["isContiguous"] is not None]
    with_evidence=sum(x["hasEvidence"] for x in details)
    return {"nodeCount":len(nodes),"nodeWithEvidenceCount":with_evidence,"fullySupportedNodeCount":sum(x["supportStatus"]=="FULLY_SUPPORTED" for x in details),"partiallySupportedNodeCount":sum(x["supportStatus"]=="PARTIALLY_SUPPORTED" for x in details),"unsupportedNodeCount":sum(x["supportStatus"]=="UNSUPPORTED" for x in details),"noEvidenceNodeCount":sum(x["supportStatus"]=="NO_EVIDENCE" for x in details),"segmentCount":segments,"exactSegmentCount":sum(sum(s["match_type"]=="EXACT" for s in x["segments"]) for x in details),"normalizedExactSegmentCount":sum(sum(s["match_type"]=="NORMALIZED_EXACT" for s in x["segments"]) for x in details),"unsupportedSegmentCount":segments-supported,"nodeSupportRate":round(sum(x["allSegmentsSupported"] for x in details)/with_evidence,3) if with_evidence else None,"segmentSupportRate":round(supported/segments,3) if segments else None,"contiguityEvaluatedNodeCount":len(eligible),"contiguousNodeCount":sum(x["isContiguous"] is True for x in eligible),"nonContiguousNodeCount":sum(x["isContiguous"] is False for x in eligible),"contiguityUnknownNodeCount":len(details)-len(eligible),"contiguousNodeRate":round(sum(x["isContiguous"] is True for x in eligible)/len(eligible),3) if eligible else None,"nodes":details}
