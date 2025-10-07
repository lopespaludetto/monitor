# Monitor de Simulações Remotas

Uma ferramenta em Python para monitorar o progresso de simulações computacionais (como STAR-CCM+) rodando em um servidor remoto via SSH. O script gera um painel de controle 2x2 atualizado periodicamente, exibindo resíduos, relatórios e imagens de cena.

## ✨ Funcionalidades

- **Monitoramento Remoto:** Conecta-se a um servidor via SSH para buscar dados em tempo real.
- **Dashboard Visual:** Gera uma imagem de painel 2x2 com:
    - Gráfico de Resíduos vs. Iteração (com zoom nas últimas 50 iterações).
    - Gráfico de Relatórios (ex: Forças, Momentos) vs. Tempo Físico.
    - Exibição das últimas imagens de cena (ex: Pressão, Velocidade).
    - Exibição de valores-chave (KPIs como Y+) como texto no gráfico.
- **Baseado em Configuração:** Todas as configurações de casos, caminhos, relatórios e credenciais são gerenciadas por um arquivo `config.json` externo, mantendo o código-fonte limpo.
- **Interface de Linha de Comando:** Controlado por argumentos simples no terminal.
- **Portátil:** Projetado para ser executado de qualquer diretório, salvando os resultados na sua pasta de trabalho atual.

## 🔧 Pré-requisitos

1.  **Python 3.8+**
2.  As bibliotecas Python necessárias. Instale-as com o pip:
    ```bash
    pip install matplotlib paramiko
    ```

## ⚙️ Configuração

#### 1. O Script (`monitor.py`)

- Coloque o arquivo `monitor.py` em uma pasta central para suas ferramentas.
- **Importante:** Adicione o caminho desta pasta à variável de ambiente `PATH` do seu sistema. Isso permite que o script seja chamado de qualquer lugar no terminal.

#### 2. O Arquivo de Configuração (`config.json`)

- Na sua pasta de trabalho/análise (onde você quer salvar os gráficos), crie um arquivo chamado `config.json`.
- Use o arquivo `config.json.template` como um modelo para criar o seu. Preencha-o com suas próprias credenciais, caminhos e detalhes da simulação.

**Exemplo da estrutura do `config.json`:**
```json
{
  "caso10": {
    "user": "seu_usuario_aqui",
    "password": "sua_senha_aqui",
    "base_dir": "/home/seu_usuario/caminho/para/simulacoes/",
    "simulation_folder": "Grid0",
    "case_subfolder": "10",
    "logfile": "job_caso10@meshed.sim.log",
    "reports": [
      "Fx (N)",
      "Fy (N)",
      "Mz (N-m)",
      "Y+ maximo"
    ]
  }
}
```

## 🚀 Como Usar

1.  Abra o terminal na pasta onde você deseja salvar os gráficos de status.
2.  Certifique-se de que o seu arquivo `config.json` está nesta mesma pasta.
3.  Execute o script passando o nome do caso que você definiu no `config.json`.

**Exemplo:**
```bash
# Monitora o caso "caso10" e salva o gráfico na pasta atual (.)
python -m monitor caso10 -o .
```
- Para parar o monitoramento, pressione `Ctrl + C`.

## 👤 Autor

- **Pedro Lopes**

## 📄 Licença

Este projeto é distribuído sob a licença MIT.