#!python3
import os
import re
from time import sleep
import argparse
import json
import logging
import requests
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Функция для исполнения команды и получения её вывода c обрезанием символа конца строки
def get_command_output(command):
    """
    Функция для отрезания последнего символа перевода строки в выводе YC CLI

    Args:
        command (str): команда для выполнения

    Returns:
        str: возвращает результат
    """
    with os.popen(command) as stream:
        return stream.read().strip()

def replace_id_to_var(terraform_manifest):
    """
    Функция рекурсивно обрабатывает terrafom-манифест, заменяя значения всех ключей,
    которые оканчиваются на '_id[s]', на 'var.<имя_ключа>'.

    Args:
        terraform_manifest (str): многострочный манифест

    Returns:
        content(str): возвращает результат
    """
    # Шаблон для замены как одиночных значений, так и списков
    pattern = r'(\b\w*_id[s]?)\s*=\s*(\[.*?\]|".*?")'

    # Функция для замены значений, включая учет списков
    def repl(m):
        key = m.group(1)  # Название ключа, например, subnet_ids или security_group_id
        # Учтем весь список или одиночное значение в скобках - возвращаем одну переменную
        logging.debug(f"replace_id_to_var: {key} = var.{key}")
        return f"{key} = var.{key}"

    # Применяем шаблон и выполняем замену
    content = re.sub(pattern, repl, terraform_manifest, flags=re.DOTALL)
    return content

def resource_tfstate_import(subitem_type,subitem_id,subitem_name):
    """
    Функция для импорта ресурса в Terraform state.

    Args:
        subitem_type (str): тип импортируемого ресурса
        subitem_id (str): ID импортируемого ресурса
        subitem_name (str): имя импортируемого ресурса

    Returns:
        resource_name(list): массив с именем ресурса в Terraform state
    """
    if service_tf == "storage":
        import_command = f"terraform import yandex_{service_tf}_{subitem}.{subitem_name} {subitem_name}"
        manifest = f"resource \"yandex_{service_tf}_{subitem_type}\" \"{subitem_name}\" {{\n\t{subitem}\t= \"{subitem_name}\"\n  }}\n"
        resource_name = [subitem_name]
    else:
        manifest = f"resource \"yandex_{service_tf}_{subitem_type}\" \"{subitem_name}_{id}\" {{\n\tname=\"{subitem_name}\"\n\t}}\n\n"
        import_command = f"terraform import yandex_{service_tf}_{subitem_type}.{subitem_name}_{id} {subitem_id}"
        resource_name = [f'{subitem_name}_{id}']

    with open(f"yc_{service_tf}_{subitem_type}_{id}_{subitem_type}.tf","w") as wfile:
        wfile.write(manifest)
    import_result=get_command_output(import_command)
    logging.debug(f"resource_tfstate_import: Manifest:{manifest}\nImport command:{import_command}\nImport Result:{import_result}")
    sleep(1)
    os.remove(f"yc_{service_tf}_{subitem_type}_{id}_{subitem_type}.tf")
    logging.debug(f"resource_tfstate_import: resource_name:{resource_name}")
    logging.info(f"Import success: resource {service_tf}_{subitem_type} with name:{resource_name}")
    return resource_name

def format_value(value):
    """
    Функция форматирует значения ключей для манифеста:
    - многострочные значения и cимволы " для размещении значение одной строкой;
    - переводим в нижний регистр булевые значения;
    - превращаем None в "";

    Args:
        value (str): исходное значение

    Returns:
        value (str): обработанное значение
    """
    if isinstance(value, str):
        if "\n" in value:
            escaped = value.replace('\n', '\\n').replace('"', '\\"')
            logging.debug (f"format_value: Multistring 2 string: {value}")
            return f'"{escaped}"'
        else:
            return f'"{value}"'
    elif isinstance(value, list):
        # Обрабатываем список, устраняя лишние кавычки в форматировании строк
        logging.debug (f"format_value: format items in list: {value}")
        return f"[{', '.join(format_value(item) for item in value)}]"
    elif isinstance(value, bool):
        logging.debug (f"format_value: format upper2lower value: {value}")
        return str(value).lower()
    elif value is None:
        logging.debug (f"format_value: replace Value None to ''")
        return '""'
    return json.dumps(value)

def get_keys_by_mask(dict_, mask):
    """
    Функция получения значений ключа по маске имени.

    Args:
        dict_ (dict): исходный JSON в виде словаря или списка
        mask (str): маска имени ключа

    Returns:
        values: значение найденноо ключа
    """
    return [value for key, value in dict_.items() if mask in key]

def remove_keys(json_data, target_key, keys2remove):
    """
    Функция рекурсивного удаления ключей в JSON данные.

    Args:
        json_data (dict,list): исходный JSON в виде словаря или списка
        target_key (str): ключ для рекурсивного поиска блока, где нужно удалить нужные ключи
        keys2remove (dict): словарь ключей, которые нужно удалить
    """
    if not target_key:  # Если список ключей пуст, удаляем из корня.
        logging.debug(f"remove_keys: is root of JSON")
        for key in list(json_data.keys()):
            logging.debug(f"remove_keys: check {key} in root!")
            if key in keys2remove:
                logging.debug(f"remove_keys: REMOVE {key} from root!")
                del json_data[key]
        return
    if isinstance(json_data, dict):
        logging.debug(f"remove_keys: data is dict {json_data}")
        # Итерируем по ключам в словаре
        for key, value in json_data.items():
            if key == target_key and isinstance(value, list):
                logging.debug(f"remove_keys: Find {key} in list")
                # Обрабатываем список, если найден нужный ключ
                for item in value:
                    if isinstance(item, dict):
                        logging.debug(f"remove_keys: item {item} is dict")
                        for remove_key in keys2remove:
                            logging.debug(f"remove_keys: remove key {remove_key} in {target_key}")
                            item.pop(remove_key, None)
            # Рекурсивно обходим вложенные структуры
            elif isinstance(value, (dict)):
                logging.debug(f"remove_keys: Find {key} in dict or list")
                remove_keys(value, target_key, keys2remove)
    elif isinstance(json_data, list):
        logging.debug(f"remove_keys: keys is list {json_data}")
        # Применяем функцию ко всем элементам списка
        for item in json_data:
            if isinstance(item, (dict)):
                logging.debug(f"remove_keys: data {item} is dict or list")
                remove_keys(item, target_key, keys2remove)

def add_keys(json_data, target_key, keys2add):
    """
    Функция рекурсивного добавления ключей в JSON данные.

    Args:
        json_data (dict,list): исходный JSON в виде словаря или списка
        target_key (str): ключ для рекурсивного поиска блока, где нужно добавить новые элементы, если None – добавляем в корень
        keys2add (list): словарь ключей и значений, которые нужно добавить {new_key: new_value}
    """
    if not target_key:  # Если target_key None, добавляем в корень.
        logging.debug(f"add_keys: is root of JSON")
        if isinstance(json_data, dict):
            logging.debug(f"add_keys: data is dict: {json_data}")
            json_data.update(keys2add)
        elif isinstance(json_data, list):
            logging.debug(f"add_keys: data is list: {json_data}")
            for item in json_data:
                if isinstance(item, dict):
                    item.update(keys2add)
        return

    if isinstance(json_data, dict):
        logging.debug(f"add_keys: data in {target_key} is dict: {json_data}")
        # Итерируем по ключам в словаре
        for key, value in json_data.items():
            if key == target_key:
                logging.debug(f"add_keys: data Find {target_key} in dict: {json_data}")
                if isinstance(value, dict):
                    logging.debug(f"add_keys: data in {target_key} is dict: {value}")
                    value.update(keys2add)
                elif isinstance(value, list):
                    logging.debug(f"add_keys: data is list: {value}")
                    if not value:  # Проверяем, пуст ли список
                        logging.debug(f"add_keys: list: {value} is None")
                        # Если список пуст, добавляем новый словарь с ключами и значениями
                        value.append(keys2add)
                    else:
                        for item in value:
                            logging.debug(f"add_keys: update data in: {value}")
                            if isinstance(item, dict):
                                item.update(keys2add)
                else:
                    logging.debug(f"add_keys: update data in: {value}")
                    value.update(keys2add)
            # Рекурсивно обходим вложенные структуры
            elif isinstance(value, (dict)):
                add_keys(value, target_key, keys2add)
    elif isinstance(json_data, list):
        logging.debug(f"add_keys: data in {target_key} is list: {json_data}")
        # Применяем функцию ко всем элементам списка
        for item in json_data:
            if isinstance(item, (dict)):
                logging.debug(f"add_keys: data in {target_key}  is dict or list : {item}")
                add_keys(item, target_key, keys2add)

def convert_attributes_to_terraform(json_data,type_,keys2include,tabscount):
    """
    Рекурсивная функция для преобразования JSON ресурса в манифест Terraform.

    Args:
        json_data (dict,list): исходный JSON в виде словаря или списка
        type_ (str): тип обрабатываемого ресурса
        keys2include (list): словарь ключей, которые нужно оставить
        tabscount (str): количество символом табуляции для читабельного форматирования манифеста

    Returns:
        terraform_str(str): форматированая строка для манифеста Terraform
    """
    terraform_str = ""
    for key, value in json_data.items():
        if value is not None and (not isinstance(value, list) or len(value) > 0) and (not isinstance(value, str) or (value != "" and value != "\"\"")) and value != "type_unspecified" or "password" in key:
            if isinstance(value, list) and len(value) > 1 and all(isinstance(item, dict) for item in value):
                logging.debug(f"convert_attributes_to_terraform: Value is list and len>1: {key} - {value}")
                for item in value:
                    terraform_str += f"{tabscount}{key} {{\n{convert_attributes_to_terraform(item,type_,keys2include,f'{tabscount}\t')}{tabscount}}}\n"
            elif isinstance(value, dict):
                logging.debug(f"convert_attributes_to_terraform: Value is dict: {key} - {value}")
                if type_ and 'clickhouse' in type_ and key == 'settings':
                    terraform_str += f"{tabscount}{key} {{\n{convert_attributes_to_terraform(value,type_,keys2include,f'{tabscount}\t')}{tabscount}}}\n"
                else:
                    terraform_str += f"{tabscount}{key} = {{\n{convert_attributes_to_terraform(value,type_,keys2include,f'{tabscount}\t')}{tabscount}}}\n"
            elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
                logging.debug(f"convert_attributes_to_terraform: Value is list of dict: {key} - {value}")
                terraform_str += f"{tabscount}{key} {{\n"
                for item in value:
                    terraform_str += f"{convert_attributes_to_terraform(item,type_,keys2include,f'{tabscount}\t')}"
                terraform_str += f'{tabscount}}}\n'
            else:
                logging.debug(f"convert_attributes_to_terraform: Value is str: {key} - {value}")
                terraform_str += f"{tabscount}{key} = {format_value(value)}\n"
    return terraform_str

def convert_to_terraform(json_data,keys2remove,keys2add,keys2include):
    """
    Генерирует код Terraform из JSON данных.

    Args:
        json_data (dict,list): исходный JSON в виде словаря или списка
        keys2remove (dict): словарь ключей, которые нужно удалить
        keys2add (dict): словарь ключей и значений, которые нужно добавить
        keys2rename (dict): словарь ключей, которые нужно переимновать сохранив исходное значение
        keys2include (dict): словарь ключей, которые нужно оставить

    Returns:
        terraform_code(str): возвращает готовый манифест ресурса
    """
    terraform_code = ""
    if "instances" in json_data and isinstance(json_data.get('instances',''), list):
        for instance in json_data.get('instances', {}):
            attributes = instance.get('attributes', {})
            type_ = json_data.get('type', '')
            name = json_data.get('name', '')
            terraform_code += f'resource "{type_}" "{name}" {{\n'
            logging.debug(f"convert_to_terraform: keys2remove from root: {keys2remove.get('root','')}")
            remove_keys(attributes, '', keys2remove.get('root',''))
            ### Этот баг чинят, когда исправят надо удалить
            if 'mdb' in type_:
                if isinstance(attributes.get('maintenance_window',''), list):
                    for elem in attributes.get('maintenance_window',''):
                        if elem.get('type','') == "ANYTIME":
                            logging.debug(f"convert_to_terraform: MDB maintenance_window remove hour: {attributes.get('maintenance_window','')}")
                            remove_keys(attributes,'maintenance_window',['hour'])
            if type_ in keys2remove.keys():
                logging.debug(f"convert_to_terraform: {type_}: keys2remove: {keys2remove.get(type_).items()}")
                for block_,key_ in keys2remove.get(type_).items():
                    logging.debug(f"convert_to_terraform: {type_}: remove: {key_} in {block_}")
                    remove_keys(attributes, block_, key_)
            if type_ in keys2add.keys():
                logging.debug(f"convert_to_terraform: {type_}: keys2add: {keys2add.get(type_)}")
                for block_,key_ in keys2add.get(type_).items():
                    logging.debug(f"convert_to_terraform: {type_}: add: {key_} in {block_}")
                    add_keys(attributes, block_, key_)
            logging.debug(f"convert_to_terraform: attributes JSON:{attributes}")
            terraform_code += convert_attributes_to_terraform(attributes,type_,keys2include,'\t')
            terraform_code += '}\n'
    return terraform_code

def get_alb_target_group_ids(json_data):
    """
    Функция для получения ID таргет-групп ALB

    Args:
        json_data (list,dict): исходный JSON в виде словаря или списка

    Returns:
        target_group_ids(list): массив с ID таргет-групп ALB
    """
    target_group_ids = []
    keys_to_check = ['http', 'stream', 'grpc']
    logging.debug(f"get_alb_target_group_ids: keys_to_check: {keys_to_check}")
    for key in keys_to_check:
        logging.debug(f"get_alb_target_group_ids: check for key: {key}")
        if key in json_data and 'backends' in json_data.get(key, ''):
            logging.debug(f"get_alb_target_group_ids: Find backends in key: {key}")
            backends = json_data.get(key, '').get('backends', '')
            for backend in backends:
                logging.debug(f"get_alb_target_group_ids: check for backend: {backend}")
                if 'target_groups' in backend and 'target_group_ids' in backend.get('target_groups', ''):
                    target_group_ids.extend(backend.get('target_groups', '').get('target_group_ids', ''))
                    logging.debug(f"get_alb_target_group_ids: Find target_group_ids {target_group_ids} in backend: {backend}")
    return target_group_ids

def get_alb_backend_group(backend_group_id):
    """
    Функция передачи бэкенд и таргет групп ALB для импорта в terraform state

    Args:
        backend_group_id (str): ID бэкенд группы ALB

    Returns:
        resource_name_list(list): возвращает список испортированных ресурсов
    """
    resource_name_list = []
    logging.debug(f"get_alb_backend_group: backend_group_id: {backend_group_id}")
    backend_group_json = get_json_api_url(access_token, backend_group_id, service, 'backendGroup', '')
    logging.debug(f"get_alb_backend_group: {backend_group_json.get('name', '')}")
    resource_name_list += resource_tfstate_import("backend_group",backend_group_json.get('id', ''),backend_group_json.get('name', ''))
    target_group_ids=get_alb_target_group_ids(backend_group_json)
    logging.debug("get_alb_backend_group: target_groups_import")
    for target_group_id in target_group_ids:
        target_group_json = get_json_api_url(access_token, target_group_id, service, 'targetGroup', '')
        resource_name_list += resource_tfstate_import("target_group",target_group_id,target_group_json.get('name', ''))
    return resource_name_list

def get_endpoint_api(service):
    """
    Функция получения адреса API эндпоинта сервиса

    Args:
        service (srt): название сервиса

    Returns:
        service_endpoint(str): возвращает url для отправки запроса в get_json_api_url
    """
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1)
    session.mount('https://', HTTPAdapter(max_retries=retries))
    try:
        url = f"https://api.cloud.yandex.net/endpoints/{service}"
        logging.debug(f'get_endpoint_api: url:{url}')
        response = session.get(url)
        if response.status_code == 200:
            data = response.json()
            logging.debug(f'get_endpoint_api: data:{data}')
            if 'address' in data:
                service_endpoint=data.get('address', '')
            else:
                logging.error("Key 'endpoints' not found.")
        else:
            raise ValueError(f"Failed to get endpoint: {response.status_code}")
    except requests.RequestException as err:
        logging.error(f"An error occurred: {err}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка декодирования JSON {e}")
        raise
    except KeyError as e:
        logging.error(f"Key error in parsing JSON response: {e}")
        raise
    return service_endpoint

def get_json_api_url(access_token, id, service, subitem_type, uri):
    """
    Функция отправки API-запроса и получения данных в формате JSON

    Args:
        access_token (str): AUTH-токен для авторизации в API облака
        id (str): ID запрашиваемого ресурса
        service (str): название сервиса в API
        subitem_type (str): название ресурса в API
        uri (str): URL-адрес API серсиса

    Raises:
        ValueError: ошибка при выполнении действия

    Returns:
        response(): данные ресурса в JSON формате
    """
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1)
    session.mount('https://', HTTPAdapter(max_retries=retries))
    if service == "application-load-balancer": service = "apploadbalancer"
    try:
        url = f"https://{service_endpoint}/{service}/v1/{subitem_type.replace('_','')}s/{id}"
        headers = {
            "Authorization":f"Bearer {access_token}"
        }
        full_url = url + uri
        logging.debug(f'get_json_api_url: full_url:{full_url}')
        response = session.get(full_url, headers=headers)

        if response.status_code != 200:
            logging.error(f"get_json_api_url:API request failed: {response.status_code} - {response.text}")
            raise ValueError(f"API get error: {response.status_code}")
        return response.json()
    except requests.RequestException as err:
        logging.error(f"An error occurred: {err}")
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка декодирования JSON {e}")
    except KeyError as e:
        logging.error(f"Key error in parsing JSON response: {e}")
        raise

def main():

    parser = argparse.ArgumentParser(description="Ссылка на полную документацию: https://wiki.yandex-team.ru/users/silmushkin/notes/terraform-import/\n"
                                        "Программа принимает на вход следующие значения:\n", formatter_class=argparse.RawTextHelpFormatter)
    # флаги
    parser.add_argument('--import-metadata', action='store_true', help='Импорт ресурсов c блоком metadata')
    parser.add_argument('--import-ids', action='store_true', help='Импорт ресурсов c текущими id в конфигурации')
    parser.add_argument('--with-state',action='store_true', help='Сохранение текущей конфигураци ресурса в terraform state')
    parser.add_argument('--debug',action='store_true', help='Включение вывода отладочной информации')
    parser.add_argument('--recursive', action='store_true', help='Включает рекурсивный импорт связанных ресурсов')
    # Обязательные позиционные аргументы
    parser.add_argument('service', help='Вид импортируемого сервиса')
    parser.add_argument('subitem_type', help='Тип импортируемого ресурса')
    parser.add_argument('name', help='Имя импортируемого ресурса')
    parser.add_argument('id', help='ID импортируемого ресурса')
    args = parser.parse_args()
    # объявляем что работаем с глобальными переменными
    global service_tf
    global service
    global subitem_type
    global name
    global id
    global access_token
    global service_endpoint
    # получаем значения
    service = args.service
    subitem_type = args.subitem_type
    name = args.name
    id = args.id

    logging.basicConfig(
    level=logging.DEBUG if args.debug else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
    )

    logging.debug("Включен DEBUG режии")
    logging.info(f"Переменные: {service}, {subitem_type}, {name}, {id}")

    match service.split("-"):
        case "managed", "kubernetes":
            service_tf = "kubernetes"
        case "application", "load", "balancer":
            service_tf = "alb"
        case "load","balancer":
            service_tf = "lb"
        case "managed", "clickhouse" | "mysql" | "postgresql" | "mongodb" | "opensearch" | "greenplum" | "kafka" | "redis" | "sqlserver" | "elasticsearch":
            service_tf = service.replace('managed-', 'mdb_')
        case "certificate", "manager":
            service_tf = "cm"
        case _:
            service_tf = service

    subitem_type = subitem_type.replace('-','_')
    access_token = os.getenv('YC_TOKEN')
    if not access_token:
        logging.error("Переменная окружения YC_TOKEN не установлена")
        sys.exit(1)

    service_endpoint = get_endpoint_api(service)
    if not service_endpoint:
        logging.error("Не удалось получить API endpoint для сервиса")
        sys.exit(1)

    keys2include = {

    }

    keys2add = {

    }

    if not args.import_metadata:
        remove_metadata = 'metadata'
    else:
        remove_metadata = ''

    keys2remove = {
        'root': ['created_at', 'id', 'status', 'hardware_generation'],
        'yandex_cm_certificate': {
            '': ['challenges','type','updated_at', 'timeouts','issued_at','issuer','not_after','not_before','serial','subject']
        },
        'yandex_dataproc_cluster': {
            'subcluster_spec': ['id']
        },
        'yandex_vpc_network': {
            '': ['subnet_ids','default_security_group_id']
        },
        'yandex_vpc_security_group': {
            'egress': ['id'],
            'ingress': ['id']
        },
        'yandex_vpc_address': {
            '': ['reserved','used','address']
        },
        'yandex_kubernetes_cluster': {
            '': ["health",'log_group_id'],
            'master': ['cluster_ca_certificate','external_v4_address','external_v4_endpoint','external_v6_endpoint','internal_v4_address','internal_v4_endpoint','version_info','zonal']
        },
        'yandex_kubernetes_node_group': {
            '': ['instance_group_id','version_info']
        },
        'yandex_mdb_postgresql_cluster': {
            '': ['health'],
            'host': ['fqdn','role']
        },
        'yandex_mdb_postgresql_user': {
            '': ['generate_password','connection_manager']
        },
        'yandex_mdb_mysql_cluster': {
            '': ['health'],
            'host': ['fqdn']
        },
        'yandex_mdb_mysql_user': {
            '': ['generate_password']
        },
        'yandex_mdb_opensearch_cluster': {
            '': ['hosts'],
        },
        'yandex_mdb_greenplum_cluster': {
            '': ['health','sharded','master_hosts','segment_hosts']
        },
        'yandex_mdb_mongodb_cluster': {
            '': ['database','user','sharded','health'],
            'host': ['health','name']
        },
        'yandex_mdb_redis_cluster' : {
            '': ['health'],
            'host': ['fqdn']
        },
        'yandex_mdb_kafka_cluster': {
            '': ['health','host']
        },
        'yandex_mdb_clickhouse_cluster': {
            '': ['health'],
            'host': ['fqdn'],
            'user': ['connection_manager']
        },
        'yandex_compute_instance': {
            '': ['fqdn',remove_metadata],
            'network_interface': ['mac_address','nat_ip_version']
        },
        'yandex_compute_instance_group': {
            '': ['instances'],
            'instance_template': ['placement_policy',remove_metadata]
        },
        'yandex_compute_image': {
            '': ['size']
        },
        'yandex_compute_disk': {
            '': ['disk_placement_policy','product_ids']
        },
        'yandex_compute_snapshot': {
            '': ['disk_size','storage_size']
        },
        'yandex_alb_load_balancer': {
            '': ['log_group_id']
        },
        'yandex_ydb_database_serverless': {
            '': ['database_path','tls_enabled','ydb_api_endpoint','ydb_full_endpoint','document_api_endpoint']
        },
        'yandex_ydb_database_dedicated': {
            '': ['database_path','tls_enabled','ydb_api_endpoint','ydb_full_endpoint','document_api_endpoint']
        },
        'yandex_backup_policy': {
            '': ['enabled','updated_at']
        },
        'yandex_storage_bucket': {
            '': ['bucket_domain_name']
        },
        'yandex_datatransfer_transfer': {
            '': ['on_create_activate_mode']
        }
    }

    #Импорт состяния ресурса в terraform state
    resource_name_list = resource_tfstate_import(subitem_type,id,name)

    logging.info(f"service:{service}")
    #Включаем рекурсивный испорт, если установлен флаг --recursive
    if args.recursive:
        logging.info(f"Начинаем рекурсивный импорт")
        match service_tf:
            # рекурсивный импорт компонентов "mdb_postgresql" | "mdb_clickhouse" | "mdb_mysql" | "mdb_mongodb"
            case "mdb_postgresql" | "mdb_clickhouse" | "mdb_mysql" | "mdb_mongodb":
                logging.debug(f"Get {service_tf} cluster {id}")
                if subitem_type == "cluster":
                        user_list = get_json_api_url(access_token, id, service, subitem_type, '/users')
                        logging.debug(f"Get user list for {service_tf} cluster {id}: {user_list}")
                        db_list = get_json_api_url(access_token, id, service, subitem_type, '/databases')
                        logging.debug(f"Get database list for {service_tf} cluster {id}: {db_list}")
                        if isinstance(user_list, (dict)):
                            for user in user_list.get('users', ''):
                                logging.debug(f"Get user for {service_tf} cluster {id}: {user}")
                                resource_name_list += resource_tfstate_import("user",f"{id}:{user.get('name', '')}",user.get('name', ''))
                        if isinstance(db_list, (dict)):
                            for database in db_list.get('databases',''):
                                logging.debug(f"Get database for {service_tf} cluster {id}: {database}")
                                resource_name_list += resource_tfstate_import("database",f"{id}:{database.get('name', '')}",database.get('name', ''))

            # рекурсивный импорт компонентов mdb-Kafka
            case "mdb_kafka":
                logging.debug(f"Get {service_tf} cluster {id}")
                if subitem_type == "cluster":
                    user_list = get_json_api_url(access_token, id, service, subitem_type, '/users')
                    logging.debug(f"Get user list for {service_tf} cluster {id}: {user_list}")
                    if isinstance(user_list, (dict)):
                        for user_name in user_list.get('users', ''):
                            user = user_name.get('name', '')
                            logging.debug(f"Get user for {service_tf} cluster {id}: {user}")
                            resource_name_list += resource_tfstate_import("user",f"{id}:{user}",user)
                    topic_list = get_json_api_url(access_token, id, service, subitem_type, '/topics')
                    logging.debug(f"Get topic list for {service_tf} cluster {id}: {topic_list}")
                    if isinstance(topic_list, (dict)):
                        for topic_name in topic_list.get('topics',''):
                            topic = topic_name.get('name', '')
                            logging.debug(f"Get topic for {service_tf} cluster {id}: {topic}")
                            resource_name_list += resource_tfstate_import("topic",f"{id}:{topic}",topic)
                    connector_list = get_json_api_url(access_token, id, service, subitem_type, '/connectors')
                    logging.debug(f"Get connector list for {service_tf} cluster {id}: {connector_list}")
                    if isinstance(connector_list, (dict)):
                        for connector_name in connector_list.get('connectors',''):
                            connector = connector_name.get('name', '')
                            logging.debug(f"Get connector for {service_tf} cluster {id}: {connector}")
                            resource_name_list += resource_tfstate_import("connector",f"{id}:{connector}",connector)

            # рекурсивный импорт компонентов ALB
            case "alb":
                logging.debug(f"Get {service_tf} load_balancer {id}")
                if subitem_type == "load_balancer":
                    alb_json = get_json_api_url(access_token, id, service, 'loadBalancer', '')
                    logging.debug(f"Get {service_tf} load_balancer {id}: {alb_json}")
                    if isinstance(alb_json, (dict, list)):
                        for listener in alb_json.get('listeners', []):
                            if listener.get('stream', {}):
                                logging.debug(f"Get {service_tf} load_balancer {id}: backend_group : listener_stream : {listener}")
                                resource_name_list += get_alb_backend_group(listener.get('stream', '').get('handler', '').get('backendGroupId', ''))
                            if listener.get('http', {}):
                                logging.debug(f"Get {service_tf} load_balancer {id}: backend_group : listener_http : {listener}")
                                http_router_json = get_json_api_url(access_token, listener.get('http', '').get('handler', '').get('httpRouterId', ''), service, 'httpRouter', '')
                                if isinstance(http_router_json, (dict, list)):
                                    logging.debug(f"Get {service_tf} load_balancer {id}: backend_group : http_router : {http_router_json}")
                                    resource_name_list += resource_tfstate_import("http_router",http_router_json.get('id', ''),http_router_json.get('name', ''))
                                    for virtual_host in http_router_json.get('virtualHosts', []):
                                        logging.debug(f"Get {service_tf} load_balancer {id}: virtual_hosts : {virtual_host}")
                                        resource_name_list += resource_tfstate_import("virtual_host",f"{http_router_json.get('id', '')}/{virtual_host.get('name', '')}",virtual_host.get('name', ''))
                                        for route in virtual_host.get('routes', ''):
                                            logging.debug(f"Get {service_tf} load_balancer {id}: routes : {route}")
                                            if 'http' in route and 'route' in route.get('http', '') and 'backend_group_id' in route.get('http', '').get('route', ''):
                                                logging.debug(f"Get {service_tf} load_balancer {id}: get_alb_backend_group for http route {route.get('http', '').get('route', '').get('backendGroupId', '')}")
                                                resource_name_list += get_alb_backend_group(route.get('http', '').get('route', '').get('backendGroupId', ''))
                                            if 'grpc' in route and 'route' in route.get('grpc', '') and 'backend_group_id' in route.get('grpc', '').get('route', ''):
                                                logging.debug(f"Get {service_tf} load_balancer {id}: get_alb_backend_group for grpc route: {route.get('grpc', '').get('route', '').get('backendGroupId', '')}")
                                                resource_name_list += get_alb_backend_group(route.get('grpc', '').get('route', '').get('backendGroupId', ''))

            # рекурсивный импорт компонентов NLB
            case "lb":
                logging.debug(f"Get {service_tf}:{id}")
                if subitem_type == "network_load_balancer":
                    nlb_json = get_json_api_url(access_token, id, service, 'networkLoadBalancer', '')
                    logging.debug(f"Get {service_tf}: {nlb_json}")
                    for attached_target_group in nlb_json.get('attachedTargetGroups', []):
                            target_group_json = get_json_api_url(access_token, attached_target_group.get('targetGroupId', ''), service, 'targetGroup', '')
                            logging.debug(f"Get {service_tf} TG: {target_group_json}")
                            resource_name_list += resource_tfstate_import("target_group",target_group_json.get('id', ''),target_group_json.get('name', ''))

            #рекурсивный импорт datatransfer
            case "datatransfer":
                logging.debug(f"Get {service_tf}:{id}")
                datatransfer_transfer_json = get_json_api_url(access_token, id, service, 'transfer', '')
                logging.debug(f"Get {service_tf}: {id}: datatransfer_transfer_json: {datatransfer_transfer_json}")
                datatransfer_endpoint_target = get_json_api_url(access_token, datatransfer_transfer_json.get('target', '').get('id', ''), service, 'endpoint', '')
                logging.debug(f"Get {service_tf}: {id}: datatransfer_endpoint_target: {datatransfer_endpoint_target}")
                datatransfer_endpoint_source = get_json_api_url(access_token, datatransfer_transfer_json.get('source', '').get('id', ''), service, 'endpoint', '')
                logging.debug(f"Get {service_tf}: {id}: datatransfer_endpoint_source: {datatransfer_endpoint_source}")
                resource_name_list += resource_tfstate_import("endpoint",datatransfer_endpoint_target.get('id', ''),datatransfer_endpoint_target.get('name', ''))
                resource_name_list += resource_tfstate_import("endpoint",datatransfer_endpoint_source.get('id', ''),datatransfer_endpoint_source.get('name', ''))

            #рекурсивный импорт VPC network(subnets,route-tables,security-groups)
            case "vpc":
                logging.debug(f"Get {service_tf}: {id}")
                if subitem_type == "network":
                    subnets = get_json_api_url(access_token, id, service, subitem_type, '/subnets')
                    logging.debug(f"Get {service_tf} subnets: {subnets}")
                    for subnet in subnets.get('subnets',[]):
                        if 'name' in subnet:
                            resource_name_list += resource_tfstate_import("subnet",subnet.get('id', ''),subnet.get('name', ''))

            #ресурсивный импорт managed-kubernetes
            case "kubernetes":
                logging.debug(f"Get {service_tf} cluster {id}")
                if subitem_type == "cluster":
                    node_groups = get_json_api_url(access_token, id, service, subitem_type, '/nodeGroups')
                    if node_groups.get('nodeGroups', []):
                        logging.debug(f"Get {service_tf} cluster {id}: Node Groups list: {node_groups.get('nodeGroups', [])}")
                        for node_group in node_groups.get('nodeGroups', []):
                            if 'name' in node_group:
                                logging.debug(f"Get {service_tf} cluster {id}: Node Group: {node_group}")
                                resource_name_list += resource_tfstate_import("node_group",node_group.get('id', ''),node_group.get('name', ''))

            case "compute":
                logging.debug(f"Get {service_tf} instance {id}")
                if subitem_type == "instance":
                    instance_json = get_json_api_url(access_token, id, service, subitem_type, '')
                    logging.debug(f"Get {service_tf} instance {id}: instance: {instance_json}")
                    if 'diskId' in instance_json.get('bootDisk', {}):
                        disk_json = get_json_api_url(access_token, instance_json.get('bootDisk', {}).get('diskId', ''), service, 'disk', '')
                        logging.debug(f"Get {service_tf} instance {id}: bootDisk:{disk_json}")
                        resource_name_list += resource_tfstate_import("disk",disk_json.get('id', ''),disk_json.get('name', ''))
                    if instance_json.get('secondaryDisks', []):
                        logging.debug(f"Get {service_tf} instance {id}: secondaryDisks list :{instance_json.get('secondaryDisks', [])}")
                        for secondary_disk in instance_json.get('secondaryDisks', []):
                            disk_json = get_json_api_url(access_token, secondary_disk.get('diskId', ''), service, 'disk', '')
                            logging.debug(f"Get {service_tf} instance {id}: secondaryDisk:{disk_json}")
                            resource_name_list += resource_tfstate_import("disk",disk_json.get('id', ''),disk_json.get('name', ''))

    try:
        with open('terraform.tfstate', 'r') as tfstate:
            json_data = json.load(tfstate)
    except Exception as e:
        logging.error(f"Ошибка работы с tfstate: {str(e)}")
        raise
    except json.JSONDecodeError as er:
        logging.error(f"Ошибка декодирования JSON: {er}")
        raise
    except (FileNotFoundError, PermissionError) as e:
        logging.error(f"Ошибка загрузки файла tfstate: {e}")
        raise

    for resource_name in resource_name_list:
        logging.debug(f"resource_mame:{resource_name.strip()}")
        for resource in json_data.get('resources', ''):
            if resource.get('name','') == resource_name.strip():
                logging.debug(f"resource:{resource}")
                terraform_manifest = convert_to_terraform(resource,keys2remove,keys2add,keys2include)
                #Если не установлен флаг --import-ids, заменяем ID связанных ресурсов на переменные var, которые необходимо прописать в файл terraform.tfvars
                if not args.import_ids:
                    terraform_manifest=replace_id_to_var(terraform_manifest)
                with open(f"{resource.get('type', '')}_{resource_name}.tf", 'w') as file:
                    file.write(terraform_manifest)
                    logging.info(f"Write manifest file:{resource.get('type', '')}_{resource_name}.tf")
                #Если не установлен флаг --with_state, удаляем из tfstate данные импортированных ресурсов
                if not args.with_state:
                    state_rm_command = get_command_output(f"terraform state rm {resource.get('type', '')}.{resource_name}")
                    logging.debug(state_rm_command)
                break

    logging.info("Compile manifest success!")

service_tf = ""
service = ""
subitem_type = ""
name = ""
id = ""
access_token = ""
service_endpoint = ""

if __name__ == "__main__":
    main()
