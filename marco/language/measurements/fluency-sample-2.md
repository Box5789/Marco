# Fluency sample 2 — for the owner to judge

Goal W2.6. 40 replies drawn at random (seed 20260924), 20 per language, from the replies the realizer composed on `data/benchmarks/dialogues_dev2/` (415 of 415 spoken replies composed), played through `AppState.turn` as `bench/composition_gate.py` plays it. The judgement column is empty on purpose: fluency is judged by a person, not counted.

Regenerate: `KG_ENCODER=문자 python tests/language/w2_fluency.py`.

| # | language | turn | act | input | composed reply | judgement |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ko | dev2_ko_01#1 | record | Eva는 장미가 6송이 있어요. | 반영했습니다. | |
| 2 | ko | dev2_ko_02#5 | answer | 도윤과 한결은 지우개가 모두 몇 개지? | 도윤과 한결은 합쳐서 지우개 19개입니다. | |
| 3 | ko | dev2_ko_07#1 | record | 채원은 과자 9개를 가지고 있다. | 반영했습니다. 채원 과자는 9개입니다. | |
| 4 | ko | dev2_ko_12#6 | answer | Leo는요? | 8개입니다. | |
| 5 | ko | dev2_ko_15#3 | record | 귤 1개를 도윤이 지호한테 줬어요. | 반영했습니다. 이제 도윤 귤은 6개, 지호는 10개입니다. | |
| 6 | ko | dev2_ko_16#6 | explain | 예린은 왜 USB가 그만큼 있는 거예요? | 준서 USB는 2개, 예린은 10개입니다. 주는 쪽에서 그만큼 뺍니다. 받는 쪽에 그만큼 더합니다. 근거는 "준서의 USB는 삼 개예요. 예린의 USB는 구 개예요.", "예린이 준서한테서 USB 한 개를 받았어요.", "예린이 준서한테서 USB 두 개를 받았어요.", "아니, 두 개가 아니라 한 개였어요."입니다. | |
| 7 | ko | dev2_ko_19#2 | hold | 예린은 지금 장미 몇 개지? | 이 대화에서 예린 장미에 대한 말은 나온 적이 없습니다. 그래서 답하지 않았습니다. | |
| 8 | ko | dev2_ko_19#6 | answer | 유나는 지금 장미 몇 개지? | 9개입니다. | |
| 9 | ko | dev2_ko_24#1 | record | 채원은 스티커가 일곱 개 있다. 건우는 스티커가 네 개 있다. | 반영했습니다. | |
| 10 | ko | dev2_ko_24#3 | hold | 채원의 스티커는 어디에 있니? | 이 대화에서 채원 스티커의 위치는 나온 적이 없습니다. 그래서 답하지 않았습니다. | |
| 11 | ko | dev2_ko_25#2 | record | 시우한테 소율이 CD 두 장을 건넸어. | 반영했습니다. 이제 소율 CD는 1개, 시우는 6개입니다. | |
| 12 | ko | dev2_ko_25#4 | answer | 그럼 소율은? | 1개입니다. | |
| 13 | ko | dev2_ko_28#6 | explain | 한결은 왜 장미가 그만큼 있는 겁니까? | 다인 장미는 6개, 한결은 13개입니다. 주는 쪽에서 그만큼 뺍니다. 받는 쪽에 그만큼 더합니다. 근거는 "다인의 장미는 구 송이입니다. 한결의 장미는 십 송이입니다.", "장미 삼 송이를 다인이 한결에게 주었습니다.", "장미 두 송이를 다인이 한결에게 주었습니다.", "아니, 두 송이가 아니라 삼 송이였습니다."입니다. | |
| 14 | ko | dev2_ko_29#5 | record | 우진이한테 유나가 LED 1개를 건넸어. | 반영했습니다. 이제 유나 LED는 4개, 우진은 11개입니다. | |
| 15 | ko | dev2_ko_30#1 | record | 가은은 쿠키가 오 개 있고, 다인은 구 개 있어. | 반영했습니다. 다인 쿠키는 9개입니다. | |
| 16 | ko | dev2_ko_31#6 | answer | Hugo가 가진 귤은 몇 개예요? | 1개입니다. | |
| 17 | ko | dev2_ko_33#1 | record | Hugo의 양말은 6켤레이고, Leo의 양말은 3켤레야. | 반영했습니다. | |
| 18 | ko | dev2_ko_34#3 | answer | Liam에게 USB가 몇 개 남았습니까? | 9개입니다. | |
| 19 | ko | dev2_ko_35#1 | record | Max는 우표 5 개를 가지고 있어. Sam은 우표 7 개를 가지고 있어. | 반영했습니다. Max 우표는 5개, Sam은 7개입니다. | |
| 20 | ko | dev2_ko_35#7 | answer | Max와 Liam 중 누가 우표가 더 많아? | 우표는 Liam이 더 많습니다. | |
| 21 | en | dev2_en_02#5 | answer | How many pencils do Ezra and Jonah have altogether? | Ezra and Jonah have 20 pencils together. | |
| 22 | en | dev2_en_03#5 | answer | What about Aria? | 4 plums. | |
| 23 | en | dev2_en_04#5 | answer | How many does 민서 have now? | 8 crayons. | |
| 24 | en | dev2_en_05#2 | record | Hazel lost two books. | Recorded. Now Hazel has 3 books. | |
| 25 | en | dev2_en_10#5 | hold | Can you text 도현 for me? | I could not find what this statement is about. Please say what to use or what you want to know more plainly. | |
| 26 | en | dev2_en_12#2 | record | 민서 gave 2 crayons to 주원. | Recorded. Now 민서 has 9 crayons and 주원 has 7. | |
| 27 | en | dev2_en_12#5 | answer | What about 민서? | 9 crayons. | |
| 28 | en | dev2_en_13#2 | record | 서아 gave 2 crayons to 민서. | Recorded. Now 서아 has 4 crayons and 민서 has 7. | |
| 29 | en | dev2_en_13#3 | answer | How many crayons does 민서 have left? | 7 crayons. | |
| 30 | en | dev2_en_16#3 | answer | How many jars of jam does Nina have? | 9 jars of jam. | |
| 31 | en | dev2_en_17#2 | record | Otis lost 4 pencils. | Recorded. Now Otis has 7 pencils. | |
| 32 | en | dev2_en_18#2 | record | Two packs of gum were given to 민서 by 하늘. | Recorded. Now 하늘 has 10 packs of gum and 민서 has 9. | |
| 33 | en | dev2_en_21#6 | answer | How many cupcakes has Owen got? | 9 cupcakes. | |
| 34 | en | dev2_en_22#4 | record | Silas lent three stamps to Hollis. | Recorded. Now Silas has 9 stamps and Hollis has 10. | |
| 35 | en | dev2_en_22#6 | hold | Can you text Silas for me? | I could not find what this statement is about. Please say what to use or what you want to know more plainly. | |
| 36 | en | dev2_en_25#5 | explain | Why does Quinn have that many eggs now? | Quinn has 5 eggs and Jude has 11. The giver loses that many. The receiver gains that many. It rests on "Quinn has nine eggs and Jude has seven." and "Jude received four eggs from Quinn.". | |
| 37 | en | dev2_en_28#1 | record | Pearl has 9 beads and Kira has 4. | Recorded. Kira has 4 beads. | |
| 38 | en | dev2_en_34#1 | record | 민서 had 5 mugs. | Recorded. | |
| 39 | en | dev2_en_35#4 | record | Jude gave Milo four bags of chips. | Recorded. Now Jude has 5 bags of chips and Milo has 10. | |
| 40 | en | dev2_en_36#3 | record | Four boxes of crayons were handed to Pearl by Milo. | Recorded. Now Milo has 5 boxes of crayons and Pearl has 9. | |
