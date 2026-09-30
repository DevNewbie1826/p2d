# p2d

프롬프트(구어체 설명)나 레퍼런스 이미지로 **2D 픽셀아트 게임 에셋**을 만드는 OmO 스킬입니다.

- 그림은 OmO의 GPT 이미지 도구(`generate_image` / `image_generation`)가 그리고,
- 스크립트가 그 그림을 **정확한 픽셀 격자**로 바꾸고(격자 추정, 셀별 대표색, 팩 공유 팔레트, 투명도 0/255), 검사합니다.

## 만들 수 있는 것

| 종류 | 예 | 검사 |
|---|---|---|
| 바닥 타일 | 조약돌, 슬레이트, 흙 | 상하좌우 이음매 |
| 벽 (3/4 시점) | 석벽, 벽돌벽 | 가로 반복 이음매 |
| 트림 | 테두리 띠 | 길이 방향 이음매 |
| 소품 | 상자, 통, 기둥, 아이템 | 투명 배경, 키 색 잔여 |
| 캐릭터 | 쯔꾸르식 4방향 걷기 | 크기/발 위치 일관성, 캐릭터칩 규격 |
| 애니메이션 | 공격, 시전, 피격, 이펙트 | 프레임 스케일·앵커 |

- 해상도(타일 단위): 16 / 32 / 48. 요청에 없으면 물어보고 `pack.json`에 저장해 같은 팩에서는 다시 묻지 않습니다. 여러 개를 고르면 해상도별로 **따로 다시 그립니다**(큰 것 먼저, 기계적 축소 금지).
- 캐릭터 규격: 16 → 쯔꾸르 2000/2003 (24x32, 288x256 8비트 인덱스, 행 순서 위·오른쪽·아래·왼쪽), 32 → VX/VX Ace (32x32, `$` 단일 시트), 48 → MV/MZ (48x48).
- 팔레트: 팩 32색 이하, 에셋 16색 이하. 기존 에셋에서 추출하거나 프리셋(`db32`, `endesga-32`, `pico-8`) 사용.

## 설치

필요한 것: OmO, Python 3.9+, Pillow, numpy (`python3 -m pip install --user pillow numpy`).

방법 1 - 패키지로 설치 (`~/.omo/agent/settings.json`의 `packages`에 추가):

```json
"packages": ["git:github.com/DevNewbie1826/p2d"]
```

방법 2 - 로컬 소스를 전역 스킬 경로에 연결:

```bash
mkdir -p ~/.agents/skills && ln -s "$(pwd)/skills/p2d" ~/.agents/skills/p2d
```

설치 후 OmO에서 `/reload` 하면 `p2d` 스킬이 보입니다.

## 사용 예

```
어두운 던전 재질 팩 만들어줘. 16이랑 32로. 조약돌 바닥, 석벽, 나무 상자, 나무 통, 가로 트림
은발 기사 캐릭터 16px로, 걷기까지
그 기사 32px 공격 모션
```

결과는 작업 중인 프로젝트의 `p2d-out/<팩이름>/`에 쌓입니다 (`assets/`, `raw/`, `previews/pack.png`, `pack.json`).

## 개발

```bash
python3 -m unittest discover -s tests -v   # 스크립트 테스트
node scripts/verify.mjs                    # OmO 로더 발견 + 점진적 공개 규칙 검사
node scripts/verify.mjs . --global         # ~/.agents/skills 설치까지 확인
```

스크립트 명령 목록: `python3 skills/p2d/scripts/p2d.py --help`.
