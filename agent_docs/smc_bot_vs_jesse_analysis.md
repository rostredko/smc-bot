# smc-bot vs Jesse: Анализ соответствия и стратегия open-source

> Дата: 2026-05-01  
> Версии: Jesse 2.0.1 | smc-bot ~1.1.0-dev  
> Цель: оценить готовность smc-bot к open-source, используя Jesse как эталон production-сервиса.

---

## 1. Краткий вывод

smc-bot — это **специализированная SMC/ICT trading platform**, а не universal algo-trading framework. Это принципиальное различие с Jesse, и именно оно определяет стратегию выхода в open-source.

**Пытаться повторить Jesse 1-в-1 — ошибка.** Jesse уже выиграл нишу "я сам пишу стратегии на Python". smc-bot занимает другую нишу: "я хочу торговать по Smart Money Concepts, не умея программировать". Это разные пользователи, разные ценности, разные продукты.

Ключевые проблемы перед открытием кода:
1. **Engine** построен на Backtrader (legacy, ~2019), а не на собственном — это технический долг и зависимость.
2. **`server.py` (2538 строк)** — God Object, неприемлемый для контрибьюторов open-source.
3. **Только Binance, только paper** — ограниченная аудитория.
4. **Нет community-стратегии** — без Discord/YouTube/docs проект умрёт сразу после публикации.

Сильные стороны, которые дают шанс:
- Уникальный **SMC/ICT domain** (BOS, CHoCH, FVG, OB — Jesse этого не умеет)
- **Integrated dashboard** с trade-by-trade walkthrough
- Детальная **внутренняя документация и TDD-культура**
- **OCO ghost-trade fix** — оригинальный технический вклад
- **Trade narrator** (человекочитаемые объяснения сделок)
- Украинский рынок — незанятая ниша

---

## 2. Обзор продуктов

### Jesse
| Аспект | Описание |
|--------|----------|
| Тип | Pip-пакет / framework для написания стратегий |
| Engine | Собственный с нуля (store + broker + candle pipeline) |
| Strategy API | Декларативный: `should_long()`, `go_long()`, `should_cancel_entry()` |
| Индикаторы | 175+ встроенных |
| Режимы | backtest, live, optimize (Optuna), monte carlo, ML pipeline, benchmark |
| Биржи | Binance, Hyperliquid, Apex, Bitfinex и другие через drivers |
| Уведомления | Telegram, Slack, Discord |
| UI | Вэб-дашборд (встроенный статик в пакете) |
| Распределение | `pip install jesse` |
| Реальная торговля | Да (с 2021) |
| Community | Discord, YouTube, JesseGPT, официальная документация |

### smc-bot
| Аспект | Описание |
|--------|----------|
| Тип | Docker-приложение / all-in-one trading platform |
| Engine | Обёртка над Backtrader (third-party) |
| Strategy API | Backtrader imperative: `next()`, `notify_order()`, `notify_trade()` |
| Индикаторы | TA-Lib через системную библиотеку |
| Режимы | backtest (single + optimize grid search), paper live |
| Биржи | Binance only |
| Уведомления | Нет |
| UI | React dashboard (Vite, MUI, Plotly) |
| Распределение | Docker Compose (self-hosted) |
| Реальная торговля | Нет (planned) |
| Community | Нет |

---

## 3. Детальное сравнение по измерениям

### 3.1 Качество Engine

**Jesse: 10/10**  
Собственный движок, написанный с нуля. Нет look-ahead bias по дизайну (гарантия фреймворка). Полный контроль над execution semantics. Поддерживает spot/futures, leverage, partial fills, liquidation simulation.

**smc-bot: 5/10**  
Обёртка над Backtrader (последний крупный релиз ~2019, слабо поддерживается). Следствие — наследуются баги фреймворка:
- `bt_oco_patch.py` существует именно потому, что Backtrader не обрабатывает OCO same-bar корректно
- `_build_forced_final_close_record` — 80-строчный хак для финализации позиций
- `TradeNarrator.duration_days` — баг из-за matplotlib float-формата Backtrader (TD-22)
- Deprecated `datetime.utcnow` в 7 местах (TD-23)

Зависимость от Backtrader — это стратегический риск. Если Jesse завтра поддержит SMC стратегии через плагин, smc-bot потеряет преимущество при этом неся legacy-долг.

**Рекомендация:** В долгосрочной перспективе рассмотреть миграцию ядра на собственный engine или использование Jesse как execution backend (smc-bot как SMC-стратегии поверх Jesse).

### 3.2 Strategy API

**Jesse:**
```python
class GoldenCross(Strategy):
    def should_long(self):
        return ta.ema(self.candles, 8) > ta.ema(self.candles, 21)

    def go_long(self):
        qty = utils.size_to_qty(self.balance * 0.05, self.price)
        self.buy = qty, self.price
        self.take_profit = qty, self.price * 1.2
        self.stop_loss = qty, self.price * 0.9
```
Декларативный, читаемый, 10 строк для рабочей стратегии.

**smc-bot:**
```python
class BTPriceAction(BaseStrategy):
    def next(self):
        # 1342 строки логики, вперемешку signal/filter/order
        if self._check_structure_filter():
            if self._check_choch_trigger():
                if self._detect_pattern():
                    # order placement...
```
Imperative Backtrader-style. `bt_price_action.py` — 1342 строки. Контрибьютору сложно понять, где начинается и где заканчивается одна ответственность.

**Для open-source это критично:** чем проще добавить свою стратегию, тем больше контрибьюторов.

### 3.3 Optimization (backtesting режим)

**Jesse:** Optuna с Bayesian optimization, walk-forward out-of-the-box, hyperparameters через `self.hp`.

**smc-bot:** Grid search (Cartesian product) по 3 параметрам (risk_reward_ratio, sl_buffer_atr, trailing_stop_distance). Нет Optuna, нет walk-forward (запланировано в roadmap).

**Gap:** средний. Grid search достаточен для 3-5 параметров, но при расширении стратегий станет combinatorial explosion. Walk-forward — критический пробел перед заявлениями о "profitability".

### 3.4 Dashboard / UI

**Jesse: 7/10** — функциональный дашборд, charts, backtest results, live monitoring. Но это скорее utility UI.

**smc-bot: 9/10** — здесь реальное преимущество:
- **Trade-by-Trade Walkthrough** — пошаговый разбор каждой сделки с OHLCV-чартом, entry/exit/SL/TP, индикаторами, нарративом
- **Config Diff** — при сравнении бэктестов выделяются изменённые параметры
- **Config Templates** с drag-and-drop reorder
- **State Restoration** после перезагрузки страницы (live сессия восстанавливается)
- **Reconnect & Resume** — авторесоединение WS с backoff
- **History Panel** с детализацией по запускам

Это именно то, что нужно пользователю который **анализирует** стратегию, а не только программирует.

### 3.5 SMC/ICT Domain

**Jesse: 3/10** — нет встроенных SMC инструментов (BOS, CHoCH, FVG, OB, ликвидность). Это gap в Jesse.

**smc-bot: 9/10:**
- `market_structure.py` — чистый, переиспользуемый модуль BOS/CHoCH/fractal detection
- `bt_price_action.py` — HTF structure + LTF execution с 40+ параметрами
- `fvg_sweep_choch_strategy.py` — FVG + sweep + CHoCH стратегия
- POI zones, OTE filter, CHoCH displacement filter, liquidity sweep detection (в roadmap)
- Trade narrative с объяснением каждого сигнала

**Это основная ценностная ниша smc-bot** и её нужно защищать и развивать.

### 3.6 Test Coverage

**Jesse: 9/10** — 32 test-файла на core, обширное тестирование order lifecycle (150+ TestStrategy-классов в strategies/).

**smc-bot: 8/10** — 38 backend test-файлов, 295 passing tests, TDD-культура задокументирована в CLAUDE.md. Это **хороший показатель** для проекта такого масштаба. Слабые места: frontend (11 файлов), live E2E opt-in, TA-Lib интеграция частично скипается.

### 3.7 Open Source Readiness

**Jesse: 10/10** — pip-пакет, `pip install jesse`, подробная документация, Discord, YouTube.

**smc-bot: 4/10:**

| Критерий | Статус |
|----------|--------|
| Установка без Docker | ❌ Нет (требует Python venv + TA-Lib C lib + MongoDB) |
| Документация для контрибьютора | ⚠️ Есть agent_docs, но нет публичного Contributing guide |
| Чистота API для внешних стратегий | ❌ Нет (Backtrader-bound, 1342-строч. файл) |
| Сервер.py читаемость | ❌ 2538 строк God Object |
| Реальная торговля | ❌ Нет (paper only) |
| Multi-exchange | ❌ Binance only |
| Notifications | ❌ Нет |
| Community | ❌ Нет |
| Changelog / Release notes | ✅ Есть (release-notes/) |
| Лицензия | ❌ Не видна в корне |

---

## 4. Что Jesse делает правильно (и стоит перенять)

### 4.1 PyPI / CLI-first distribution
Jesse устанавливается за 2 минуты. smc-bot требует Docker + TA-Lib + MongoDB. Для украинского пользователя без DevOps-опыта — барьер входа слишком высок.

**Action:** Сделать `pip install backtrade-machine` с режимом lite (SQLite вместо MongoDB, без Docker).

### 4.2 Declarative strategy API
Чем проще написать новую стратегию, тем больше сообщество. Jesse: 10 строк. smc-bot: нужно знать Backtrader + OCO patch + BaseStrategy internals.

**Action:** После Phase 4 (domain decomposition) — создать `SMCStrategy` base class с чистым API: `detect_structure()`, `find_poi()`, `entry_trigger()`.

### 4.3 Walk-forward validation
Без walk-forward нельзя заявлять что стратегия "работает", а не overfit. Jesse имеет это из коробки. В smc-bot запланировано но не реализовано.

**Action:** Приоритизировать в Phase 1.1.0 выше "Live Session Status Panel".

### 4.4 Notifications (Telegram)
Любой trading bot должен уметь слать сигналы в Telegram. Это zero-cost feature с высоким perceived value.

**Action:** Добавить Telegram notifier (100 строк кода) до open source.

### 4.5 Community-first approach
Jesse: Discord (тысячи участников), YouTube (десятки видео), JesseGPT. Это не опциональный маркетинг — это product.

**Action:** Завести Ukrainian Telegram-канал / Discord перед публикацией кода.

---

## 5. Уникальные преимущества smc-bot (не копировать Jesse, а развивать своё)

### 5.1 SMC/ICT как первоклассный гражданин
Jesse думает в категориях EMA/RSI/MACD. smc-bot думает в категориях BOS/CHoCH/FVG/OB/Liquidity. Это разные языки описания рынка. Выиграть можно только став "the SMC platform", а не "ещё один backtest-фреймворк".

**Roadmap:** Публичная библиотека SMC-стратегий. Marketplace стратегий для украинского сообщества.

### 5.2 Integrated "Research → Paper → Live" pipeline
Jesse тоже это умеет, но smc-bot имеет лучший dashboard для analysis phase. Уникальность: trade-by-trade walkthrough + narrative + config diff. Это "research workbench" для SMC трейдера.

### 5.3 Ukrainian market focus
- WhiteBIT (украинская биржа, топ-5 в Европе по объёму) — нет поддержки в Jesse
- UAH/USDT пары
- Украинская документация и support
- Потенциал для интеграции с украинскими crypto-exchanges

### 5.4 OCO Patch как вклад в экосистему
`bt_oco_patch.py` — это реальный contribution к Backtrader-экосистеме. Стоит оформить как отдельный pip-пакет (`backtrader-oco-fix`) и опубликовать. Это даёт visibility в Backtrader-сообществе и SEO.

### 5.5 Trade Narrator
Автоматическое объяснение каждой сделки текстом — это уникальная фича. Jesse этого нет. Потенциал: интеграция с LLM для более детального анализа ("почему эта сделка выглядит так?").

---

## 6. Технические долги критичные для open-source

Согласно `TECHNICAL_DEBT_REPORT.md`, Phase 1 (guardrails) завершена 2026-04-19. Для open-source необходимо минимум Phase 2 + Phase 3:

| Долг | Критичность для OS | Описание |
|------|--------------------|----------|
| TD-01 + TD-25 | **БЛОКЕР** | `server.py` 2538 строк, `run_backtest_task` ~391 строка. Контрибьютор не сможет разобраться. |
| TD-02 | **БЛОКЕР** | Runtime state в module-level globals. Невозможно запустить 2 инстанса или написать тест без побочных эффектов. |
| TD-05 | **HIGH** | `bt_price_action.py` 1342 строки — страшно редактировать |
| TD-03 | **HIGH** | Config normalization дублируется в 3 местах |
| TD-15 | **MEDIUM** | `data_loader.py` 650 строк, 4 ответственности |
| TD-12/13/14 | LOW | Дублирование `safe_float`, `_safe_max_drawdown`, analyzer setup |
| TD-23 | LOW | Deprecated datetime calls (7 мест) |

**Минимальный уровень для open-source:**
- [x] Phase 1 (done)
- [ ] Phase 2: runtime registry + config translation seam
- [ ] Phase 3: server.py extraction (backtest/live runners)
- [ ] Лицензионный файл в корне (MIT/Apache)

---

## 7. Матрица соответствия Jesse

| Измерение | Jesse | smc-bot | Разрыв | Приоритет |
|-----------|-------|---------|--------|-----------|
| Custom engine | ✅ Полностью своё | ⚠️ Backtrader wrapper | Высокий | Long-term |
| Strategy API simplicity | ✅ Declarative | ⚠️ Imperative BT | Высокий | Phase 4+ |
| Indicator library | ✅ 175+ | ⚠️ TA-Lib only | Высокий | Medium-term |
| Optimization quality | ✅ Optuna + WF | ⚠️ Grid search | Средний | Phase 1.1.0 |
| Dashboard UX | ✅ Good | ✅ Better (SMC) | Преимущество smc-bot | Keep |
| SMC domain | ❌ None | ✅ Strong | Преимущество smc-bot | Core moat |
| Test coverage | ✅ Extensive | ✅ 295 tests | Малый | Good |
| Open source DX | ✅ pip install | ⚠️ Docker only | Высокий | Pre-launch |
| Community | ✅ Discord/YT | ❌ None | Критический | Before launch |
| Documentation | ✅ docs.jesse.trade | ⚠️ Internal only | Высокий | Pre-launch |
| Multi-exchange | ✅ 10+ | ❌ Binance only | Высокий | Phase 1.2 |
| Real trading | ✅ Production | ❌ Paper only | Средний | Q3 2026 |
| Notifications | ✅ Tg/Slack/Discord | ❌ None | Высокий | Pre-launch |
| Monte Carlo | ✅ Built-in | ❌ Not yet | Средний | Nice-to-have |
| ML pipeline | ✅ scikit-learn | ❌ Not yet | Низкий | Long-term |
| Walk-forward | ✅ Built-in | ❌ Planned | Высокий | Phase 1.1.0 |

---

## 8. Рекомендуемая стратегия выхода в open-source

### Позиционирование
**НЕ:** "Ещё один algo-trading framework"  
**ДА:** "The Smart Money Concepts trading platform — для тех, кто торгует по ICT/SMC методологии"

Целевая аудитория: SMC-трейдеры, которые хотят бэктестировать свои идеи без написания кода. На Украине это тысячи людей в Telegram-каналах про ICT, Inner Circle Trader, Smart Money.

### Phased open-source план

**Фаза 0 — Подготовка (до публикации):**
- [ ] Завершить Phase 2 (runtime seams) + Phase 3 (server.py extract)
- [ ] Добавить Telegram notifier
- [ ] Написать публичный README (EN + UA)
- [ ] Contributing guide
- [ ] LICENSE файл (MIT)
- [ ] Добавить walk-forward backtest
- [ ] Завести Telegram-канал / Discord сообщества

**Фаза 1 — Soft launch:**
- [ ] Опубликовать репозиторий (GitHub)
- [ ] Написать статью/тред на UA crypto-форумах
- [ ] WhiteBIT exchange driver (Ukrainian exchange, killer feature для UA рынка)
- [ ] Видео-демо на YouTube (UA/EN)

**Фаза 2 — Community growth:**
- [ ] Marketplace стратегий (users submit SMC strategies)
- [ ] Telegram alerts для live сигналов
- [ ] pip install / lite mode (без Docker)
- [ ] Walk-forward + Monte Carlo (credibility для серьёзных трейдеров)

**Фаза 3 — Monetization:**
- [ ] SaaS hosted version (как Jesse имеет платные premium features)
- [ ] Managed cloud backtest (за вычислительные ресурсы)
- [ ] Strategy marketplace с платными стратегиями

---

## 9. Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Jesse добавляет SMC стратегии | Средняя | Высокое | Быстрее занять нишу, глубже в domain |
| Backtrader как legacy bottleneck | Высокая | Высокое | Долгосрочно: собственный engine или Jesse-as-backend |
| Нет traction без community | Высокая | Критическое | Сначала community, потом open source |
| Конкуренция с paid SMC tools (TradingView Premium, Quantconnect) | Средняя | Средняя | Open source + self-hosted = privacy advantage |
| Server.py complexity отпугнёт контрибьюторов | Высокая | Высокое | Phase 2-3 до открытия |
| TA-Lib C dependency сложна для установки | Высокая | Средняя | Docker как primary + lite mode без TA-Lib |

---

## 10. Итог

smc-bot — это **хорошо написанный, хорошо задокументированный** проект с понятным видением, реальной тест-культурой и уникальной SMC-нишей. Команда знает свои долги и имеет план их погашения.

**Основные проблемы перед open-source:**
1. Backtrader как фундамент — технический потолок (долгосрочный риск)
2. `server.py` God Object — барьер для контрибьюторов (решается Phase 2-3)
3. Paper-only — снижает доверие ("работает ли это в реале?")
4. Нет community — без него open-source = мёртвый репозиторий

**Главное отличие от Jesse:** Jesse — это *framework* для программистов. smc-bot — это *платформа* для SMC-трейдеров. Это разные продукты. Выиграть можно только в своей нише.

**Ближайшие шаги перед публикацией:**
1. Phase 2 + Phase 3 (server.py refactor) — убрать главный барьер для контрибьюторов
2. Walk-forward validation — обязательно для credibility
3. Telegram notifier — 100 строк, огромный perceived value
4. Публичный README + Contributing guide
5. Завести community (Telegram-канал) **до** публикации кода
