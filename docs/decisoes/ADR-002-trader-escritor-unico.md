# ADR-002 — Risk Engine e Execution no mesmo processo (`trader`), escritor único de ordens

**Status:** aceita (2026-11-17)

**Contexto:** o CLAUDE.md exige que toda ordem passe pelo Risk Engine e que a execução seja um módulo independente. Se risco e execução fossem processos separados ligados por fila, uma mensagem forjada ou reprocessada poderia chegar à execução sem checagem de risco, e duas decisões concorrentes poderiam furar limites.

**Decisão:**
- `risk/` e `execution/` são **módulos** separados, com testes próprios, mas rodam no **mesmo processo**.
- `execution.submit()` só aceita um objeto `ApprovedOrder`, que apenas o Risk Engine sabe construir.
- Os sinais são processados em série.
- Só esse processo recebe a chave de trading.
- O sistema é **fail-closed**: o boot começa em `BLOCKED`, e se não conseguir ler o estado do kill switch, assume que ele está ativo.

**Consequências:**
- O `trader` é um ponto único de falha. Isso é aceitável: se ele cair, nenhuma ordem nova sai, que é o modo seguro, e os stops já colocados na exchange continuam valendo.
- O reinício precisa ser rápido e sempre seguido de reconciliação.
