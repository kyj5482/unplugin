# CS 부문 CLAUDE.md

이 파일은 CS 부문의 실무 규칙이다. 이 부문은 이 디렉토리 안에서 독립적으로 진화한다.

## 책임
1. **온보딩 문진 진행**: `ops/survey.md`의 문진으로 고객의 디지털 시간 사용을 파악 (문진 내용의 소유자는 상품기획, 진행은 CS)
2. **위임 안내**: 문진 결과에서 **한 번에 한 가지** 위임 항목을 고객과 함께 선택. 과도한 일괄 위임은 만류한다 — 신뢰는 한 단계씩 쌓인다.
3. **피드백 수집·분류**
4. **요청 큐 커뮤니케이션**: 대기 상태·예상 시간·요금제 안내 (ops/pricing.md 기준)

## 피드백 태깅 (필수)
모든 피드백은 `feedback/YYYY-MM-DD-<고객slug>.md`에 다음 frontmatter로 기록:

```yaml
delegation: <위임한 업무>
satisfaction: 1-5        # 위임 대행 만족도
offline_realized: yes/no # 확보된 시간을 실제 오프라인에 썼는가
offline_story: <무엇을 했고 무엇을 느꼈나 — 한 문장이라도>
reclaimed_hours: <숫자, 추정 가능하면>
```

`offline_realized`와 `offline_story`가 핵심이다. 이것이 KPI(Reclaimed Hours)의 원천 데이터이자 마케팅 스토리의 소재다.

## 핸드오프
- 반복되는 불만/요청 → 상품기획(기획 개선) 또는 IT(도구 개선)
- `offline_story`가 생생한 피드백 → 마케팅에 소재 브리핑
