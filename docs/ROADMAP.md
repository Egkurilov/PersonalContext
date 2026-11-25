# Roadmap v1.3 — порядок реализации и трассировка

25.11.2026. Добавлен [Personal Intelligence Engine](INTELLIGENCE.md), PC-026–035. Первые полезные локальные рекомендации не зависят от внешнего исследования. Владелец исключил Apple-specific collectors (PC-006 и PC-008 закрыты not planned, FR-03 зарезервирован). 33 активные задачи, ID неизменяемы. Стек пересмотрен: нативное Python Windows-приложение, SQLite/FTS5/NumPy, встроенный Uvicorn, asyncio durable jobs, PyInstaller/Inno Setup. [ADR-011](adr/011-native-windows-python.md) нормативен; no Docker/WSL/PostgreSQL/Rust. Chrome/Edge — основной сбор браузера; обычный Chrome macOS browser-only, без Apple-specific разработки. Веб-портал доступен на всех устройствах. Не включать Apple задачи в release gate. P0 = обязательная основа, P1 = обязательный функционал v1 или явно capability-gated (PC-024). Приоритет не заменяет зависимости.

## Матрица
| PC-ID | Issue | Этап | Приоритет | Требования | Зависит от PC (номера) | Назначение |
|---|---|---|---|---|---|---|
| PC-001 | [#1](https://github.com/Egkurilov/PersonalContext/issues/1) | R0 | P0 | FR-15 | — | Python Windows app, packaging, CI |
| PC-002 | [#2](https://github.com/Egkurilov/PersonalContext/issues/2) | R0 | P0 | FR-13,07 | 1 | Авторизация, pairing, policy |
| PC-003 | [#3](https://github.com/Egkurilov/PersonalContext/issues/3) | R0 | P0 | FR-07 | 1,2 | SQLite ledger и durable jobs |
| PC-004 | [#4](https://github.com/Egkurilov/PersonalContext/issues/4) | R1 | P0 | FR-01,07,13 | 2,3 | Python tray / lifecycle / browser delivery |
| PC-005 | [#5](https://github.com/Egkurilov/PersonalContext/issues/5) | R1 | P0 | FR-01 | 4 | Windows foreground/idle |
| PC-006 | [#6](https://github.com/Egkurilov/PersonalContext/issues/6) | — | excluded | — | — | Нативный macOS — закрыто not planned |
| PC-007 | [#7](https://github.com/Egkurilov/PersonalContext/issues/7) | R1 | P0 | FR-02 | 2,3,4 | Chrome/Edge MV3 |
| PC-008 | [#8](https://github.com/Egkurilov/PersonalContext/issues/8) | — | excluded | — | — | Safari/macOS/iOS — закрыто not planned |
| PC-009 | [#9](https://github.com/Egkurilov/PersonalContext/issues/9) | R1 | P0 | FR-04,05 | 2,3 | Исторический импорт |
| PC-010 | [#10](https://github.com/Egkurilov/PersonalContext/issues/10) | R1 | P1 | FR-05 | 7 | Видео playback |
| PC-011 | [#11](https://github.com/Egkurilov/PersonalContext/issues/11) | R1 | P0 | FR-07,04,05 | 3,5,7,9 | Нормализация и timeline API |
| PC-012 | [#12](https://github.com/Egkurilov/PersonalContext/issues/12) | R1 | P0 | FR-13 | 2,3,4,11 | Privacy lifecycle |
| PC-013 | [#13](https://github.com/Egkurilov/PersonalContext/issues/13) | R1 | P0 | FR-12,13 | 1,2,7,9,11,12 | Portal foundation, timeline, sources, privacy |
| PC-014 | [#14](https://github.com/Egkurilov/PersonalContext/issues/14) | R2 | P0 | FR-08 | 3,11,12,26 | Local AI pipeline |
| PC-015 | [#15](https://github.com/Egkurilov/PersonalContext/issues/15) | R2 | P0 | FR-09 | 11,12,14 | Scoring и topic corrections |
| PC-016 | [#16](https://github.com/Egkurilov/PersonalContext/issues/16) | R2 | P0 | FR-09,12 | 13,15 | Карта интересов |
| PC-017 | [#17](https://github.com/Egkurilov/PersonalContext/issues/17) | R2 | P0 | FR-10,12 | 11,13,14,15 | Знания, проекты, намерения |
| PC-018 | [#18](https://github.com/Egkurilov/PersonalContext/issues/18) | R2 | P0 | FR-09,12 | 13,15,16,17 | Dashboard |
| PC-019 | [#19](https://github.com/Egkurilov/PersonalContext/issues/19) | R2 | P0 | FR-11 | 11,12,14,17 | FTS5 + NumPy hybrid search |
| PC-020 | [#20](https://github.com/Egkurilov/PersonalContext/issues/20) | R2 | P0 | FR-11,12 | 13,14,19 | AI assistant |
| PC-021 | [#21](https://github.com/Egkurilov/PersonalContext/issues/21) | R3 | P1 | FR-11,14 | 2,12,15,17,19 | MCP |
| PC-022 | [#22](https://github.com/Egkurilov/PersonalContext/issues/22) | R3 | P1 | FR-10,14 | 12,17,18 | Obsidian export |
| PC-023 | [#23](https://github.com/Egkurilov/PersonalContext/issues/23) | R3 | P1 | FR-09,12,14,16 | 15,17,18,20,26,30,31 | Insights/digests |
| PC-024 | [#24](https://github.com/Egkurilov/PersonalContext/issues/24) | R4 | P1 | FR-06,13 | 4,5,12,14,26 | Optional Windows OCR |
| PC-025 | [#25](https://github.com/Egkurilov/PersonalContext/issues/25) | R4 | P0 | Все активные FR | Все активные кроме себя, включая 35; 24 capability-gated | Release gate |
| PC-026 | [#26](https://github.com/Egkurilov/PersonalContext/issues/26) | R1 | P0 | FR-23,15 | 1,3,4 | Resource Governor |
| PC-027 | [#27](https://github.com/Egkurilov/PersonalContext/issues/27) | R2 | P0 | FR-18,13 | 12,17,19 | Long-Term Memory |
| PC-028 | [#28](https://github.com/Egkurilov/PersonalContext/issues/28) | R2 | P0 | FR-19,10 | 15,17,27 | Goal Engine |
| PC-029 | [#29](https://github.com/Egkurilov/PersonalContext/issues/29) | R2 | P1 | FR-20,09 | 15,17,19,27,28 | Knowledge Discovery |
| PC-030 | [#30](https://github.com/Egkurilov/PersonalContext/issues/30) | R2 | P0 | FR-16,12 | 13,15,18,19,26,27,28,29 | Recommendation Engine |
| PC-031 | [#31](https://github.com/Egkurilov/PersonalContext/issues/31) | R2 | P0 | FR-21,16 | 12,28,30 | Feedback Engine |
| PC-032 | [#32](https://github.com/Egkurilov/PersonalContext/issues/32) | R3 | P0 | FR-17,23 | 2,12,19,26,28,30 | Research Agent |
| PC-033 | [#33](https://github.com/Egkurilov/PersonalContext/issues/33) | R3 | P1 | FR-17,20 | 28,30,32 | Technology Radar |
| PC-034 | [#34](https://github.com/Egkurilov/PersonalContext/issues/34) | R3 | P1 | FR-20,12 | 17,19,27,28,29,30,31 | Context Restore |
| PC-035 | [#35](https://github.com/Egkurilov/PersonalContext/issues/35) | R4 | P0 | FR-16–21,23,24 | 23,26–34 | Recommendation Evaluation |

## Порядок поставки
- **R0**: #1 → #2 → #3, синтетический SQLite ledger, native bundle smoke и security baseline; реальный сбор запрещён.
- **R1**: #4→#5, #7, #9; #10 после #7; #11 после collectors/import; #12 privacy gate; #13 интерфейс. #26 после #4, до тяжёлого AI/OCR/research; до закрытия #12 только синтетические данные. R1 можно использовать как прозрачную хронологию, без обещания AI карты.
- **R2**: #14→#15→#16; #17 после #15; #18 после #16/#17; #19 после #17; #20 после #19. Полноценная карта, знания, поиск и локальный ассистент. Затем #27→#28→#29→#30→#31; первое полезное local-only решение, уже можно начать добровольный двухнедельный пилот.
- **R3**: #21, #22, #23 после соответствующих upstream задач. MCP и Obsidian выключены до явной настройки; #23 использует единый feed #30/#31. #32→#33 — внешнее исследование только при explicit endpoint opt-in; #34 после local recommendations.
- **R4**: #24 только после privacy PoC; если защита невозможна, capability явно disabled, тесты fail-closed. #35 — eval recommendation quality после #23 и #26–34, технические gates; #25 после #35 блокирует выпуск до полного E2E, benchmark, eval, SQLite backup/restore, чистая Windows EXE install/upgrade/uninstall, документации и подтверждения владельца.

## Покрытие требований
| FR | Issues |
|---|---|
| FR-01 | #4 #5 |
| FR-02 | #7 |
| FR-03 | excluded (not planned) |
| FR-04 | #9 #11 |
| FR-05 | #9 #10 #11 |
| FR-06 | #24 capability-gated |
| FR-07 | #2 #3 #4 #11 |
| FR-08 | #14 |
| FR-09 | #15 #16 #18 #23 |
| FR-10 | #17 #22 |
| FR-11 | #19 #20 #21 |
| FR-12 | #13 #16 #17 #18 #20 #23 |
| FR-13 | #2 #4 #12 #13 #24 |
| FR-14 | #21 #22 #23 |
| FR-15 | #1 #25 #26 |
| FR-16 | #23 #30 #31 #35 |
| FR-17 | #32 #33 #35 |
| FR-18 | #27 #35 |
| FR-19 | #28 #35 |
| FR-20 | #29 #33 #34 #35 |
| FR-21 | #31 #35 |
| FR-23 | #26 #32 #35 |
| FR-24 | #35 #25 |

Каждая активная задача имеет аналитику, зависимости, DoD и приёмочные сценарии; общий DoD в AGENTS.md. Не закрывать задачу без PR и доказательств тестирования. Перед началом выбирается первая open задача с закрытыми prerequisites; параллелить только независимые модули. Все NFR проверяются в #25, recommendation quality gates в #35; opt-in real pilot не выдавать за выполненный тест без данных. Изменение требований только через ADR и обновление SPEC/CONTRACTS/матрицы/issue. 
