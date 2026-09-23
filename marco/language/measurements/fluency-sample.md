# Fluency sample — for the owner to judge

Fixed sample: every reply of the §12 dialogue in each language and dev dialogues ko-dev-04 and en-dev-04, realized with the W1-1 meaning block attached in the test. Judgement column is empty on purpose: fluency is judged by a person, not counted.

| # | dialogue | input | realized reply | judgement |
| --- | --- | --- | --- | --- |
| 1 | section12-english | Minsu has five apples, and Jiyeon has two. | Recorded. Jiyeon has 2 apples. | |
| 2 | section12-english | Minsu gave Jiyeon two. | Recorded. Minsu gave Jiyeon 2 apples. Now Minsu has 3 apples and Jiyeon has 4. | |
| 3 | section12-english | How many does Jiyeon have now? | 4 apples. | |
| 4 | section12-english | Where is that person? | This conversation never stated the location of Jiyeon. So I did not answer. | |
| 5 | section12-english | Actually, the one given was one, not two. | I changed the amount in the same event "Minsu gave Jiyeon two." from 2 to 1. No new event was added. Now Minsu has 4 apples and Jiyeon has 3. | |
| 6 | section12-english | Why did that happen? | Now Minsu has 4 apples and Jiyeon has 3. This is because of the correction "Actually, the one given was one, not two.". I changed the amount in the same event "Minsu gave Jiyeon two." from 2 to 1. No new event was added. That many is taken away (count_remove). That many is added (count_add). It rests on "Minsu has five apples, and Jiyeon has two." and "Minsu gave Jiyeon 1.". | |
| 7 | section12-english | What about the other person, not that one? | I do not know who 'that one' refers to. Which of 'Jiyeon' and 'Minsu' do you mean? | |
| 8 | section12-한국어 | 민수는 사과 다섯 개, 지연은 두 개가 있어. | [수선] "민수는 사과 다섯 개"를 "민수 사과는 다섯 개"로 읽습니다 (규칙 "구슬은 18개", '민수는'의 조사 '는'을 '사과' 뒤로 옮기기, 비용 1/2). [수선] "지연은 두 개가 있어"를 "지연은 두 개 있어"로 읽습니다 (규칙 "구슬은 18개 있다", '개가'에서 조사 '가' 빼기, 비용 1/2). 반영했습니다. 민수 사과는 5개, 지연은 2개입니다. | |
| 9 | section12-한국어 | 민수가 지연에게 두 개 줬어. | [수선] "민수가 지연에게 두 개 줬어"를 "민수가 지연에게 두 개를 줬어"로 읽습니다 (규칙 "하루가 모래에게 2개를 줬다", '개' 뒤에 조사 '를' 붙이기, 비용 1/2). 반영했습니다. 민수가 지연에게 사과 2개를 줬습니다. 이제 민수 사과는 3개, 지연은 4개입니다. | |
| 10 | section12-한국어 | 지연은 지금 몇 개야? | 4개입니다. | |
| 11 | section12-한국어 | 그 사람은 어디 있어? | [수선] "그 사람은 어디 있어"를 "그 사람은 어디에 있어"로 읽습니다 (규칙 "연필은 어디에 있어", '어디' 뒤에 조사 '에' 붙이기, 비용 1/2). 이 대화에서 지연의 위치는 나온 적이 없습니다. 그래서 답하지 않았습니다. | |
| 12 | section12-한국어 | 아까 준 건 두 개가 아니라 한 개야. | 같은 사건 "민수가 지연에게 두 개 줬어."의 수량을 2개에서 1개로 고쳤습니다. 새 사건은 더하지 않았습니다. 이제 민수 사과는 4개, 지연은 3개입니다. | |
| 13 | section12-한국어 | 왜 그렇게 됐어? | 이제 민수 사과는 4개, 지연은 3개입니다. 정정 "아까 준 건 두 개가 아니라 한 개야." 때문입니다. 같은 사건 "민수가 지연에게 두 개 줬어."의 수량을 2개에서 1개로 고쳤습니다. 새 사건은 더하지 않았습니다. 수량에서 그만큼 뺍니다 (count_remove). 수량에 그만큼 더합니다 (count_add). 근거는 "민수는 사과 다섯 개, 지연은 두 개가 있어.", "민수가 지연에게 한 개 줬어."입니다. 이 가운데 수선으로 읽은 말: "민수는 사과 다섯 개" → "민수 사과는 다섯 개"; "지연은 두 개가 있어" → "지연은 두 개 있어"; "민수가 지연에게 한 개 줬어" → "민수가 지연에게 한 개를 줬어". | |
| 14 | section12-한국어 | 그 사람 말고 다른 사람은? | '그 사람'이 누구를 가리키는지 알지 못합니다. '민수', '지연' 가운데 누구인가요? | |
| 15 | ko-dev-04 | 태린 사과는 9개 있다. | 반영했습니다. | |
| 16 | ko-dev-04 | 도하 사과는 4개 있다. | 반영했습니다. | |
| 17 | ko-dev-04 | 태린이 도하에게 사과 2개를 줬다. | 반영했습니다. 이제 태린 사과는 7개, 도하는 6개입니다. | |
| 18 | ko-dev-04 | 아까 준 건 2개가 아니라 3개야. | 같은 사건 "태린이 도하에게 사과 2개를 줬다."의 수량을 2개에서 3개로 고쳤습니다. 새 사건은 더하지 않았습니다. 이제 태린 사과는 6개, 도하는 7개입니다. | |
| 19 | ko-dev-04 | 왜 그렇게 됐어? | 이제 태린 사과는 6개, 도하는 7개입니다. 정정 "아까 준 건 2개가 아니라 3개야." 때문입니다. 같은 사건 "태린이 도하에게 사과 2개를 줬다."의 수량을 2개에서 3개로 고쳤습니다. 새 사건은 더하지 않았습니다. 수량에서 그만큼 뺍니다 (count_remove). 수량에 그만큼 더합니다 (count_add). 근거는 "태린 사과는 9개 있다.", "도하 사과는 4개 있다.", "태린이 도하에게 사과 3개를 줬다."입니다. | |
| 20 | ko-dev-04 | 도하 사과는 몇 개 남았어? | 7개입니다. | |
| 21 | en-dev-04 | Iris has 9 apples, and Felix has 4. | Recorded. Felix has 4 apples. | |
| 22 | en-dev-04 | Iris gave Felix two. | Recorded. Iris gave Felix 2 apples. Now Iris has 7 apples and Felix has 6. | |
| 23 | en-dev-04 | Actually, the one given was three, not two. | I changed the amount in the same event "Iris gave Felix two." from 2 to 3. No new event was added. Now Iris has 6 apples and Felix has 7. | |
| 24 | en-dev-04 | Why did that happen? | Now Iris has 6 apples and Felix has 7. This is because of the correction "Actually, the one given was three, not two.". I changed the amount in the same event "Iris gave Felix two." from 2 to 3. No new event was added. That many is taken away (count_remove). That many is added (count_add). It rests on "Iris has 9 apples, and Felix has 4." and "Iris gave Felix three.". | |
| 25 | en-dev-04 | How many does Felix have now? | 7 apples. | |
