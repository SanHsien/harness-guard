# 各語言與框架快速測試矩陣 (Test Matrix)

| 技術棧 | 測試指令 (Test) | 建置/型別檢查 (Build & Lint) | 推薦快速模式 |
|---|---|---|---|
| **Python** | `pytest -v` / `python -m pytest` | `ruff check .` / `mypy .` | `pytest -q -k "<case>"` |
| **Node.js (NPM)** | `npm test` | `npm run build` / `npx tsc --noEmit` | `npm test -- -t "<pattern>"` |
| **Node.js (Bun)** | `bun test` | `bun run build` / `bun x tsc --noEmit` | `bun test <file>` |
| **Node.js (Deno)** | `deno test` | `deno lint` / `deno check` | `deno test <file>` |
| **Go** | `go test -v ./...` | `go build ./...` / `golangci-lint run` | `go test -run "<TestName>" ./...` |
| **Rust** | `cargo test` | `cargo check` / `cargo clippy` | `cargo test <test_name>` |
| **.NET / C#** | `dotnet test` | `dotnet build` | `dotnet test --filter "<Name>"` |
| **Java (Maven)** | `mvn test` | `mvn compile` | `mvn test -Dtest=<Class>#<method>` |
| **Java (Gradle)** | `./gradlew test` | `./gradlew build` | `./gradlew test --tests "<Class>"` |
| **PowerShell** | `Invoke-Pester` | `Invoke-ScriptAnalyzer -Path .` | `Invoke-Pester -Tag "<Tag>"` |
