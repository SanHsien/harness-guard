# Test commands by stack

Work out which stack the project uses (look for `pyproject.toml`, `package.json`,
`go.mod`, `Cargo.toml`, a `.csproj`, `pom.xml`) and run the command from that row. When a
project defines its own script, that one wins over anything here.

| Stack | Test | Build / lint | Narrow it down |
|---|---|---|---|
| Python | `pytest -v` / `python -m pytest` | `ruff check .` / `mypy .` | `pytest -q -k "<case>"` |
| Node (npm) | `npm test` | `npm run build` / `npx tsc --noEmit` | `npm test -- -t "<pattern>"` |
| Node (Bun) | `bun test` | `bun run build` / `bun x tsc --noEmit` | `bun test <file>` |
| Node (Deno) | `deno test` | `deno lint` / `deno check` | `deno test <file>` |
| Go | `go test -v ./...` | `go build ./...` / `golangci-lint run` | `go test -run "<TestName>" ./...` |
| Rust | `cargo test` | `cargo check` / `cargo clippy` | `cargo test <test_name>` |
| .NET | `dotnet test` | `dotnet build` | `dotnet test --filter "<Name>"` |
| Java (Maven) | `mvn test` | `mvn compile` | `mvn test -Dtest=<Class>#<method>` |
| Java (Gradle) | `./gradlew test` | `./gradlew build` | `./gradlew test --tests "<Class>"` |
| PowerShell | `Invoke-Pester` | `Invoke-ScriptAnalyzer -Path .` | `Invoke-Pester -Tag "<Tag>"` |

The last column is for the loop while you are fixing something: run the one failing case
until it passes, then run the full suite once before reporting. A narrowed run is a
progress check, not the evidence.
