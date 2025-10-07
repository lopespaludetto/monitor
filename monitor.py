# ==============================================================================
# SCRIPT DE MONITORAMENTO REMOTO PARA SIMULAÇÕES STAR-CCM+
#
# Ferramenta para monitorar uma simulação remotamente via SSH, gerando um
# gráfico de status com resíduos, relatórios e imagens de cena.
#
# Autor: Gemini (com base nas solicitações do usuário)
# Versão: 1.2 (Portátil e com suporte a subpastas)
#
# Exemplo de Uso no Terminal:
# ---------------------------
# 1. Monitorar um caso com imagens em subpasta (ex: Grid0/05):
#    >> python monitor.py Grid0 05 -o C:/Caminho/Para/Salvar
#
# 2. Monitorar um caso simples (sem subpastas de imagem):
#    >> python monitor.py MinhaSimulacao
#
# 3. Ver todas as opções disponíveis:
#    >> python monitor.py --help
# ==============================================================================

import re
import os
import time
import getpass
import argparse
import posixpath
import paramiko
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.image as mpimg
import json
# ==============================================================================
# FUNÇÃO DE PARSING DO ARQUIVO DE LOG
# ==============================================================================
def parse_starccm_logfile(filepath, colunas_relatorios_especificadas):
    iterations, report_times, report_iterations = [], [], []
    residuals_data = {'Continuity': [], 'X-momentum': [], 'Y-momentum': [], 'Z-momentum': [], 'Tke': [], 'Sdr': [], 'Intermittency': []}
    reports_data = {key: [] for key in colunas_relatorios_especificadas}
    
    residual_headers_map, report_headers_map = {}, {}
    current_time = 0.0
    header_line_found = False
    iteration_data_started = False
    
    expected_residual_cols = list(residuals_data.keys())
    timestep_regex = re.compile(r"TimeStep\s+\d+:\s+Time\s+([\d.eE+-]+)")

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                match_time = timestep_regex.match(line)
                if match_time:
                    current_time = float(match_time.group(1))
                    iteration_data_started = True 
                    continue
                
                if line.startswith("Iteration") and "Continuity" in line and (not colunas_relatorios_especificadas or any(report_col in line for report_col in colunas_relatorios_especificadas)):
                    header_line_found = True
                    full_headers_list_parsed = [h.strip() for h in re.split(r'\s{2,}', line) if h.strip()]
                    temp_residual_map, temp_report_map = {}, {}
                    for i, header in enumerate(full_headers_list_parsed):
                        if header in expected_residual_cols: temp_residual_map[header] = i
                        elif header in colunas_relatorios_especificadas: temp_report_map[header] = i
                    if temp_residual_map: residual_headers_map = temp_residual_map
                    if temp_report_map: report_headers_map = temp_report_map
                    continue
                
                if header_line_found and iteration_data_started and (line.startswith(' ') or (line and line[0].isdigit())):
                    values_str = re.split(r'\s+', line.strip())
                    try:
                        if not values_str or not values_str[0].isdigit(): continue
                        iter_num = int(values_str[0])
                        iterations.append(iter_num)
                        
                        for res_name, col_idx in residual_headers_map.items():
                            residuals_data[res_name].append(float(values_str[col_idx]) if col_idx < len(values_str) else float('nan'))
                        
                        first_report_col_name = colunas_relatorios_especificadas[0] if colunas_relatorios_especificadas else None
                        first_report_col_idx = report_headers_map.get(first_report_col_name) if first_report_col_name else None
                        
                        if first_report_col_idx is not None and first_report_col_idx < len(values_str) and values_str[first_report_col_idx] not in ['---', '']:
                            report_times.append(current_time)
                            report_iterations.append(iter_num)
                            for report_name, col_idx in report_headers_map.items():
                                reports_data[report_name].append(float(values_str[col_idx]) if col_idx < len(values_str) else float('nan'))
                    except (ValueError, IndexError):
                        if iterations and (not residuals_data[expected_residual_cols[0]] or len(iterations) > len(residuals_data[expected_residual_cols[0]])):
                            for res_name in expected_residual_cols:
                                if len(residuals_data[res_name]) < len(iterations): residuals_data[res_name].append(float('nan'))
                        pass
    except FileNotFoundError:
        print(f"Erro em parse_starccm_logfile: arquivo local '{filepath}' não encontrado.")
        return [], {}, [], [], {}
    except Exception as e:
        print(f"Erro ao processar o arquivo de log '{filepath}': {e}")
        return [], {}, [], [], {}

    if iterations:
        max_len = len(iterations)
        for res_name in residuals_data:
            while len(residuals_data[res_name]) < max_len: residuals_data[res_name].append(float('nan'))
            residuals_data[res_name] = residuals_data[res_name][:max_len]
            
    return iterations, residuals_data, report_iterations, report_times, reports_data

# ==============================================================================
# FUNÇÃO AUXILIAR PARA ENCONTRAR IMAGEM REMOTA
# ==============================================================================
def find_latest_image_in_remote_folder(sftp_client, remote_folder_path):
    try:
        folder_contents = sftp_client.listdir_attr(remote_folder_path)
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
        image_files_attrs = [
            {'path': posixpath.join(remote_folder_path, attr.filename), 'mtime': attr.st_mtime}
            for attr in folder_contents if attr.filename.lower().endswith(image_extensions)
        ]
        if not image_files_attrs: return None
        return max(image_files_attrs, key=lambda x: x['mtime'])['path']
    except Exception:
        return None

# ==============================================================================
# FUNÇÃO DE PLOTAGEM (VERSÃO COM TEXTO DE STATUS)
# ==============================================================================
# ==============================================================================
# FUNÇÃO DE PLOTAGEM (VERSÃO COM TEXTO DE STATUS E EIXO Y FIXO)
# ==============================================================================
def plot_data(iterations, residuals_data, report_iterations, report_times, reports_data, 
              colunas_reports_para_plotar, sftp_client_obj, base_remote_dir, 
              output_filename=None, show_plot_interactively=True):
    
    output_dir = os.path.dirname(output_filename) if output_filename else "."
    os.makedirs(output_dir, exist_ok=True)

    if not iterations and not report_times:
        print("Nenhum dado válido para plotar.")
        return None

    fig, axs = plt.subplots(2, 2, figsize=(18, 10)) 
    
    # --- Plotagem dos Resíduos (axs[0, 0]) ---
    ax_residuals = axs[0, 0]
    ax_residuals.set_title('Resíduos vs. Iteração')
    for key, values in residuals_data.items():
        if any(v == v for v in values):
             ax_residuals.plot(iterations, values, label=key, alpha=0.8)
    ax_residuals.set_xlabel('Número da Iteração'); ax_residuals.set_ylabel('Resíduo')
    ax_residuals.set_yscale('log'); ax_residuals.grid(True, which="both", ls="--")
    
    if iterations:
        start_iter = iterations[max(0, len(iterations) - 50)]
        end_iter = iterations[-1]
        ax_residuals.set_xlim(left=start_iter, right=end_iter)

    ax_residuals.legend(loc='upper right', fontsize='small')

    # --- Plotagem dos Relatórios (axs[0, 1]) ---
    ax_reports = axs[0, 1]
    ax_reports.set_title('Relatórios vs. Tempo Físico')

    reports_to_display_as_text = ['Y+ maximo']
    reports_to_plot_as_lines = [r for r in colunas_reports_para_plotar if r not in reports_to_display_as_text]

    has_line_data = False
    for key in reports_to_plot_as_lines:
        if key in reports_data and any(v==v for v in reports_data[key]):
            ax_reports.plot(report_times, reports_data[key], label=key, marker='.', linestyle='-')
            has_line_data = True
            
    if has_line_data:
        ax_reports.set_xlabel('Tempo Físico (s)'); ax_reports.set_ylabel('Valores dos Relatórios')
        ax_reports.grid(True, which="both", ls="--")
        ax_reports.set_ylim(-100, 100) # <<< LINHA REINSERIDA AQUI
        ax_reports.legend(loc='best', fontsize='small')
    else:
        ax_reports.text(0.5, 0.5, "Sem dados de relatórios para plotar.", ha='center', va='center', transform=ax_reports.transAxes)

    y_pos = 0.95
    for key in reports_to_display_as_text:
        if key in reports_data and reports_data[key]:
            last_value = reports_data[key][-1]
            text_label = f"Último {key}: {last_value:.2f}"
            
            ax_reports.text(0.95, y_pos, text_label,
                            transform=ax_reports.transAxes,
                            fontsize=12,
                            fontweight='bold',
                            verticalalignment='top',
                            horizontalalignment='right',
                            bbox=dict(boxstyle='round,pad=0.5', fc='wheat', alpha=0.5))
            y_pos -= 0.12

    # --- Plotagem das Imagens (axs[1, 0] e axs[1, 1]) ---
    image_subfolders = {"Pressure": axs[1, 0], "Velocity": axs[1, 1]}
    for name, ax in image_subfolders.items():
        ax.axis('off')
        if sftp_client_obj and base_remote_dir:
            remote_image_folder = posixpath.join(base_remote_dir, name)
            latest_image_path = find_latest_image_in_remote_folder(sftp_client_obj, remote_image_folder)
            if latest_image_path:
                local_temp_image_path = os.path.join(output_dir, f"temp_image_{name.lower()}.png")
                try:
                    sftp_client_obj.get(latest_image_path, local_temp_image_path)
                    img_data = mpimg.imread(local_temp_image_path)
                    ax.imshow(img_data)
                    ax.set_title(f"{name} - {posixpath.basename(latest_image_path)}")
                    os.remove(local_temp_image_path)
                except Exception as e:
                    ax.text(0.5, 0.5, f"Erro ao carregar imagem\nde {name}", ha='center', va='center')
                    print(f"Erro ao processar imagem remota {latest_image_path}: {e}")
            else:
                ax.text(0.5, 0.5, f"Imagem de {name}\nNão Disponível", ha='center', va='center')
        else:
            ax.text(0.5, 0.5, "SFTP inativo", ha='center', va='center')

    plt.tight_layout(pad=2.0)
    if output_filename:
        try:
            plt.savefig(output_filename)
            print(f"Gráfico salvo como '{output_filename}'")
        except Exception as e:
            print(f"Erro ao salvar o gráfico: {e}")
    if show_plot_interactively: plt.show()
    plt.close(fig)
# ==============================================================================
# FUNÇÃO PRINCIPAL DE MONITORAMENTO (O "MOTOR")
# ==============================================================================
def monitor_simulation( 
        hostname, username, remote_log_path, case_subfolder, reports_to_plot, 
        output_filename, interval_seconds, use_key_auth, ssh_key_path,
        port_ssh=22, password=None, ssh_key_passphrase=None 
    ):
    
    output_dir = os.path.dirname(output_filename)
    local_temp_log_path = os.path.join(output_dir, "temp_downloaded_logfile.log")

    base_remote_dir_log = posixpath.dirname(remote_log_path)
    base_remote_dir_images = posixpath.join(base_remote_dir_log, case_subfolder) if case_subfolder else base_remote_dir_log

    print("Iniciando monitoramento.")
    print(f"Pasta de LOGS remota: {base_remote_dir_log}")
    print(f"Pasta de IMAGENS remota: {base_remote_dir_images}")

    while True:
        ssh_client, sftp_client = None, None
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        try:
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            print(f"Conectando a {hostname}:{port_ssh} como {username}...")
            
            if use_key_auth:
                ssh_client.connect(hostname, port=port_ssh, username=username, 
                                   key_filename=os.path.expanduser(ssh_key_path),
                                   passphrase=ssh_key_passphrase, timeout=20)
            else:
                if not password: password = getpass.getpass(f"Senha para {username}@{hostname}: ")
                ssh_client.connect(hostname, port=port_ssh, username=username, password=password, timeout=20)
            
            print("Conexão SSH bem-sucedida.")
            sftp_client = ssh_client.open_sftp()
            
            print(f"Baixando log '{remote_log_path}' para '{local_temp_log_path}'...")
            sftp_client.get(remote_log_path, local_temp_log_path)
            
            iterations, residuals, report_iters, report_times, reports = parse_starccm_logfile(local_temp_log_path, reports_to_plot)
            
            if not iterations:
                print("Nenhum dado de iteração encontrado no log. Verificando novamente...")
            else:
                plot_data(iterations, residuals, report_iters, report_times, reports,
                          reports_to_plot, sftp_client, base_remote_dir_images,
                          output_filename=output_filename, show_plot_interactively=False)

        except paramiko.AuthenticationException as e: print(f"Falha na autenticação: {e}"); break
        except paramiko.SSHException as e: print(f"Erro de SSH: {e}")
        except FileNotFoundError as e: print(f"Erro de arquivo não encontrado (remoto ou local): {e}")
        except Exception as e: print(f"Ocorreu um erro inesperado: {type(e).__name__} - {e}")
        finally:
            if sftp_client: sftp_client.close()
            if ssh_client: ssh_client.close()
        
        print(f"Aguardando {interval_seconds} segundos para a próxima atualização...")
        time.sleep(interval_seconds)

# ==============================================================================
# PONTO DE ENTRADA DO SCRIPT (LENDO TODAS AS CONFIGURAÇÕES DO JSON)
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Monitora uma simulação STAR-CCM+ remota usando um arquivo de configuração.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Argumentos principais
    parser.add_argument("case_name", help="Nome do caso a ser executado, conforme definido no arquivo de configuração.")
    parser.add_argument("-o", "--output-dir", default=".", help="Diretório onde o gráfico e arquivos temporários serão salvos.")
    parser.add_argument("--config", default="config.json", help="Caminho para o arquivo de configuração JSON.")
    
    # Argumentos que podem sobrescrever o padrão, mas não contêm dados sensíveis
    parser.add_argument("--host", default="10.1.1.218", help="Hostname ou IP do servidor SSH.")
    parser.add_argument("-i", "--interval", type=int, default=30, help="Intervalo de atualização em segundos.")
    
    args = parser.parse_args()

    # --- Leitura e Validação do Arquivo de Configuração ---
    try:
        with open(args.config, 'r') as f:
            all_configs = json.load(f)
    except FileNotFoundError:
        print(f"Erro: Arquivo de configuração '{args.config}' não encontrado.")
        exit(1)
    except json.JSONDecodeError:
        print(f"Erro: O arquivo de configuração '{args.config}' não é um JSON válido.")
        exit(1)

    case_config = all_configs.get(args.case_name)
    if not case_config:
        print(f"Erro: Caso '{args.case_name}' não encontrado em '{args.config}'.")
        print(f"Casos disponíveis: {', '.join(all_configs.keys())}")
        exit(1)
    
    # Extrai as configurações do arquivo.
    user = case_config.get("user")
    password = case_config.get("password")
    base_dir = case_config.get("base_dir")
    simulation_folder = case_config.get("simulation_folder")
    case_subfolder = case_config.get("case_subfolder")
    logfile = case_config.get("logfile")
    reports_to_plot = case_config.get("reports", [])

    # Validação dos campos obrigatórios do config
    required_keys = ["user", "password", "base_dir", "simulation_folder", "logfile"]
    if not all(key in case_config for key in required_keys):
        missing_keys = [key for key in required_keys if key not in case_config]
        print(f"Erro: A configuração para '{args.case_name}' está incompleta. Faltando as chaves: {', '.join(missing_keys)}")
        exit(1)

    # --- Montagem final e execução ---
    remote_log_full_path = posixpath.join(base_dir, simulation_folder, logfile)

    output_image_base_name = f"status_{simulation_folder}_{args.case_name}.png"
    output_image_full_path = os.path.join(args.output_dir, output_image_base_name)

    # A autenticação por chave será usada se a senha no config for nula ou vazia
    use_ssh_key = not password

    print(f"Iniciando monitoramento para o caso: '{args.case_name}'")
    print(f"Pressione Ctrl+C para interromper. Saída será salva em: {os.path.abspath(args.output_dir)}")
    
    try:
        monitor_simulation(
            hostname=args.host,
            username=user,
            password=password,
            remote_log_path=remote_log_full_path,
            case_subfolder=case_subfolder,
            reports_to_plot=reports_to_plot,
            output_filename=output_image_full_path,
            interval_seconds=args.interval,
            use_key_auth=use_ssh_key,
            ssh_key_path="~/.ssh/id_rsa"
        )
    except KeyboardInterrupt:
        print("\nMonitoramento interrompido pelo usuário.")
    except Exception as e:
        print(f"\nErro fatal na execução: {e}")