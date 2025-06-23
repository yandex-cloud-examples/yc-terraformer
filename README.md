1. ### Что это такое и зачем это нужно?
   
      Инструмент для создания `Terraform` манифестов (HCL) для существующих ресурсов в Yandex Cloud.
   
2. ### Какие преимущества дает использование утилиты?
   
      * Клиенту:
   
        * переход на управление инфраструктурой с помощью `terraform`
   
        * быстрое поднятие сервиса аналогичной конфигурации в другой зоне доступности, облаке, фолдере для последующего переноса данных и нагрузки;
   
      * Инженеру поддержки:
   
        * получение конфигураций сервисов клиента в виде файлов манифеста  `terraform`
   
        * для проведения репро возникшей у него проблемы, чем ускоряет поиск её решения
   
3. ### Как пользоваться утилитой?
   
      Последняя версия скрипта работает при условии использования версии `python` \>= `3.10`.
      Устанавливаем и настраиваем `terraform` по инструкции: https://cloud.yandex.ru/ru/docs/tutorials/infrastructure-management/terraform-quickstart#install-terraform
   
      Создаем `СА` с ролью `viewer` на облако/фолдер и генерируем для него токен по инструкции: https://yandex.cloud/ru/docs/tutorials/infrastructure-management/terraform-quickstart#get-credentials
   
      Скрипт получает при запуске сервис, тип, название и id импортируемого ресурса.
   
      {% cut "`./yc-terraformer.py -h`" %}
      
      ```
      usage: yc-terraformer.py [-h] [--import-metadata] [--import-ids] [--with-state] [--debug] [--recursive] service subitem_type name id
      
      Ссылка на полную документацию: https://github.com/yandex-cloud-examples/yc-terraformer/
      Программа принимает на вход следующие значения:
      
      positional arguments:
        service            Вид импортируемого сервиса
        subitem_type       Тип импортируемого ресурса
        name               Имя импортируемого ресурса
        id                 ID импортируемого ресурса
      
      options:
        -h, --help         show this help message and exit
        --import-metadata  Импорт ресурсов c блоком metadata
        --import-ids       Импорт ресурсов c текущими id в конфигурации
        --with-state       Сохранение текущей конфигураци ресурса в terraform state
        --debug            Включение вывода отладочной информации
        --recursive        Включает рекурсивный импорт связанных ресурсов
      ```
   
      {% endcut %}
   
   , где *`service`* - название сервиса по аналогии с их названием в `yc` (`iam`, `compute`, `managed-postgresql`, `vpс`, `application-load-balancer`, `managed-kubernetes` `etc`), *`subitem_type`* - тип ресурса по аналогии с их названием в `yc` (`service-account`, `instance`, `cluster`, `node-group` `etc`), *`name`* - название ресурса которое будет использовано для *`terraform state`* (во избежание путаницы лучше использовать имя ресурса в облаке), *`id`* - `id` импортируемого ресурса в облаке.
   
      ```
      yc-terraformer.py --import-ids --with-state --debug --recursive application-load-balancer load-balancer $ALB_name $alb_id
      yc-terraformer.py --import-ids --with-state --debug --recursive managed-postgresql cluster $cluster_name $cluster_id
      yc-terraformer.py --import-ids --with-state --debug --recursive managed-kubernetes cluster $cluster_name $cluster_id
      ```
   
      Рекурсивный импорт реализован для следующих сервисов:
   
      - `Compute` - instance, disks;
   
      - СУБД (`managed-postgresql`, `managed-clickhouse`, `managed-mysql`,`managed-mongodb`) - cluster, users, DB;
   
      - `managed-kafka`- cluster, users, topic, connector;
   
      - `NLB` - load-balancer, target-group;
   
      - `ALB` - load-balancer, http-router, virtual-host, backend-group, target-group;
   
      - `datatransfer`- transfer, endpoints;
   
      - `VPC` - network, subnets;
  
      На основе полученных данных создаются манифест файлы под каждый тип ресурса с его именем и `ID`.
   
      По умолчанию все значения `ID` заменяются на переменную с аналогичным именем параметра, чтобы случайно не внести изменения в импортируемые ресурсы. Для указания значений переменных, используемых в файле манифеста, нужно создать файл `variables.tf`, в котором их нужно объявить, и файл `terraform.tfvars`, в котором они будут назначены.
   
      {% cut "`variables.tf`" %}
      
      ```
      #=========== main ==============
      variable "cloud_id" {
        description = "The cloud ID"
        type        = string
      }
      variable "folder_id" {
        description = "The folder ID"
        type        = string
      }
      variable "default_zone" {
        description = "The default zone"
        type        = string
        default     = "ru-central1-a"
      }
      variable "zone" {
        description = "zone"
        type        = string
      }
      variable "key_id" {
        description = "key_id"
        type        = string
      }
      variable "platform_id" {
        description = "platform_id"
        type        = string
      }
      variable "service_account_id" {
        description = "service_account_id"
        type        = string
      }
      variable "node_service_account_id" {
        description = "Service account ID for node groups"
        type        = string
      } 
      #=========== network ==============
      variable "network_id" {
        description = "id of main network"
        type        = string
      }
      variable "subnet_id" {
        description = "subnet_id"
        type        = string
      }
      variable "subnet_ids" {
        description = "subnet_ids"
        type        = list(string)
      }
      variable "security_group_ids" {
        description = "security_group_ids"
        type        = list(string)
      }
      ```
   
      {% endcut %}
   
      {% cut "`terraform.tfvars`" %}
      
      ```
      cloud_id  = "b1g5q8h52km0rg0tf67a"
      folder_id = "b1gabqsuc5jl0q3ppd0n"
      zone      = "ru-central1-a"
      vpc_network = "enpa5vuod13q30aavn7a"
      vpc_subnets = {
        ru-central1-a = "e9bvenpi3ukdfq5r2v0q"
        ru-central1-b = "e2lsif6dp433q1vv8svt"
        ru-central1-c = "b0cckti034jmj1enji2t"
      }
      service_account_id      = "ajeqidn8h6aqa1qtt5g9"
      node_service_account_id = "ajeqidn8h6aqa1qtt5g9"
      key_id = "abj5dkbk3u7nh9gt7abj"
      security_group_ids = [
                  "enptg0u7g9fb89h5p08j",
                  ]
      subnet_ids = [
                      "e9b3ecmd0kbpbd2mtid1",
                  ]
      cluster_id = ""
      disk_id     = ""
      network_id  = ""
      subnet_id = "e9b3ecmd0kbpbd2mtid1"
      log_group_id = ""
      http_router_id = ""
      backend_group_id  = ""
      platform_id = "standard-v3"
      ```
   
      {% endcut %}
   
      Если вы импортируете ресурсы клиента, используя флаги `--import-metadata`, `--import-ids` или `--with-state`, будьте предельно аккуратны, чтобы случайно не применить изменения на ресурсы клиента после корректировки файла манифеста. Крайне рекомендуется после выполнения необходимых манипуляций удалять файлы манифестов, а также импортированные ресурсы из `terraform state`.
   
4. ### Механизм работы:
   
      Для импорта информации об имеющейся облачной инфраструктуре, используется механизм `terraform import`, который записывает данные в файл `terraform.tfstate`, где будет храниться актуальное состояние ресурсов импортируемых сервисов. Далее берём этот файл и парсим как словарь `JSON`, в результате получаем манифест файл необходимого ресурса, удалив предварительно параметры и блоки создаваемые автоматически и не управляемые пользователем.
   
      Проверяем командой `terraform plan -target=<название_стейта_ресурса>`, что полученный манифест файл соответствует правильному описанию состояния ресурса. Если возникают какие-то сообщения об ошибке, нужно внести необходимые корректировки. При обнаружении таких ситуаций, просьба завести тикет на `BUG`.
   
      Запускаем `terraform plan` и убеждаемся, что запланированных изменений нашего ресурса нет. Мы успешно импортировали конфигурацию ресурса в манифест файл `terraform`.
   
5. ### Список поддерживаемых сервисов и типов ресурсов:

   * {% cut "iam - Yandex Identity and Access Manager resources" %}
     
     * role
   
     * service-account
   
     * key
   
     * access-key
   
     * api-key
   
     * user-account
   
     {% endcut %}
   
   * {% cut "compute                   Yandex Compute Cloud resources" %}
     
     * instance
   
     * disk
   
     * image
   
     * snapshot
   
     * snapshot-schedule
   
     * instance-group
   
     * placement-group
   
     * host-group
   
     * disk-placement-group
   
     * filesystem
   
     * gpu-cluster
   
     {% endcut %}
   
   * {% cut "vpc                        Yandex Virtual Private Cloud resources" %}
     
     * network
   
     * route-table
   
     * security-group
   
     * subnet
   
     * address
   
     * gateway
   
     {% endcut %}
   
   * {% cut "dns                        Yandex DNS resources" %}
     
     * zone
   
     * bind-file
   
     {% endcut %}
   
   * {% cut "managed-kubernetes         Kubernetes clusters" %}
     
     * cluster
   
     * node-group
   
     {% endcut %}
   
   * {% cut "ydb                        YDB databases" %}
     
     * database\_serverless
   
     * database\_dedicated
   
     {% endcut %}
   
   * {% cut "kms                        Yandex Key Management Service resources" %}
     
     * symmetric-key
   
     * asymmetric-encryption-key
   
     * asymmetric-signature-key
   
     {% endcut %}
   
   * {% cut "cdn                        CDN resources" %}
     
     * resource
   
     * origin-group
   
     * origin
   
     {% endcut %}
   
   * {% cut "certificate-manager        Certificate Manager resources" %}
     
     * certificate
   
     {% endcut %}
   
   * {% cut "managed-clickhouse         ClickHouse clusters" %}
     
     * cluster
   
     * user
   
     * database
   
     {% endcut %}
   
   * {% cut "managed-mongodb            MongoDB clusters" %}
     
     {% block %}
     
     * cluster
   
     * database
    
     * user
   
     {% endblock %}
   
     {% endcut %}
   
   * {% cut "managed-mysql              MySQL clusters" %}
     
     * cluster
   
     * database
   
     * user
   
     {% endcut %}
   
   * {% cut "managed-sqlserver          SQLServer clusters" %}
     
     * cluster
   
     {% endcut %}
   
   * {% cut "managed-postgresql         PostgreSQL clusters" %}
     
     * cluster
   
     * database
   
     * user
   
     {% endcut %}
   
   * {% cut "managed-greenplum          Greenplum clusters" %}
     
     * cluster
   
     {% endcut %}
   
   * {% cut "managed-redis              Redis clusters" %}
     
     * cluster
   
     {% endcut %}
   
   * {% cut "managed-kafka              Apache Kafka clusters, topics, users and connectors" %}
     
     * cluster
   
     * topic
   
     * user
   
     * connector
   
     {% endcut %}
   
   * {% cut "container                  Container resources" %}
     
     * registry
   
     * registry\_iam\_binding
   
     * repository
   
     * repository\_iam\_binding
   
     * image
   
     * repository\_lifecycle\_policy
   
     {% endcut %}
   
   * {% cut "load-balancer              Yandex Load Balancer resources" %}
     
     * network-load-balancer
   
     * target-group
   
     {% endcut %}
   
   * {% cut "datatransfer               Data Transfer endpoints and transfers" %}
     
     * transfer
   
     * endpoint
   
     {% endcut %}
   
   * {% cut "serverless                 Serverless resources" %}
     
     * function
   
     * trigger
   
     * api-gateway
   
     * container
   
     * mdbproxy
   
     * network
   
     {% endcut %}
   
   * {% cut "iot                        Yandex IoT Core resources" %}
     
     * registry
   
     * broker
   
     * device
   
     {% endcut %}
   
   * {% cut "dataproc                   data processing clusters" %}
     
     * cluster
   
     * subcluster
   
     * job
   
     {% endcut %}
   
   * {% cut "application-load-balancer  Yandex Application Load Balancer resources" %}
     
     * load-balancer
   
     * backend-group
   
     * http-router
   
     * virtual-host
   
     * target-group
   
     {% endcut %}
   
   * {% cut "logging                    Yandex Cloud Logging" %}
     
     * group
   
     * sink
   
     {% endcut %}
   
   * {% cut "storage                    Yandex Object Storage resources" %}
     
     * bucket
   
     {% endcut %}
   
   * {% cut "backup                     Yandex Cloud Backup resources" %}
     
     * vm
   
     * backup
   
     * policy
   
     {% endcut %}
   
  7. ### Примеры использования (возможные варианты, ситуации)
   
      1. С его помощью можно:
   
         * перевести управление ресурсами с `UI` на `terraform`;
   
         * сохранить себе манифест конфигурации ресурсов, чтобы в случае чего заново развернуть их в этом или другом облаке/фолдере;
   
         * создание тестовых ресурсов аналогичных конфигурации прода для проведения репро и тестирований;
   
         * разобраться, как с помощью `terraform` провести точечную настройку любого поддерживаемого ресурса в облаке при опыте настройки только через `UI`;
   
      2. Пример использования в связке с `YC CLI`:
   
         1. для импорта всех ресурсов сервиса одного типа в фолдере:
   
            ```
            yc <service> <subitem_type> list –-format json | jq -r '.[] | "\(.name) \(.id)"' | xargs -n 2 ./yc-terraformer.py --with-state --import-ids --import-metadata --recursive <service> <subitem_type> 
            ```
   
         2. аналогичным способом можно получить список фолдеров в облаке и прогнать их в цикле по всем сервисам добавив к команде yc ключи `--cloud-id` и `–-folder-id`:
   
            ```
            yc resource-manager folder list --format json --cloud-id <cloud-id> | jq -r '.[].id' | xargs -n 1 yc <service> <subitem_type> list –-format json –-folder-id| jq -r '.[] | "\(.name) \(.id)"' | xargs -n 2 ./yc-terraformer.py --with-state --import-ids --import-metadata --recursive <service> <subitem_type> 
            ```
   
            , где `<service>` - имя сервиса, а `<subitem_type>` - тип ресурса, по аналогии с описанными выше параметрами подаваемыми на вход.
   
      3. Кейсы инженера поддержки:
   
         * От клиента поступил вопрос, как с помощью `terraform` манифеста провести точечную настройку какого-то ресурса в облаке. Если не знакомы с `terraform`, то можно импортировать их ресурс в манифест файл, развернуть копию ресурса у себя в фолдере, провести ручную настройку через `UI`, внеся необходимые изменения, после чего снова провести импорт ресурса в манифест файл. На выходе получим манифест с нужными параметрами для `terraform`;
   
         * Клиент обратился с проблемой при проведении каких-либо операций с ресурсами через `terraform/UI/YC CLI/API`, просит разобраться, где проблема. Импортируем необходимые ресурсы в манифесты `terraform`, разворачиваем у себя копию его инфраструктуры и производим описанные им действия, с которыми у него возникают проблемы. Разбираемся в чем дело, имея доступ ко всем необходимым для диагностики инструментам;
   
         * У клиента при попытке обновления какого-то ресурса, выполнение `terraform plan` предлагает пересоздать весь ресурс, либо внести какие-либо не предусмотренные манифестом изменения. В качестве проверки такого поведения, можно импортировать конфигурацию ресурса в `terraform` манифест и изменив параметр, проверить на этом же кластере вывод `terraform plan`, если всё нормально, свериться с их планом и проверить не изменились ли какие-то параметры с момента создания манифеста;
   
      4. Кейсы клиента
   
         * Во время инцидента с отказом одной из зон доступности, где оказалась основная инфраструктура клиента, можно быстро импортировать конфигурацию всех критичных ресурсов и развернуть их копию в рабочей зоне для переноса нагрузки;
   
         * Создание резервной копии конфигурации ресурсов текущей инфраструктуры, для быстрого восстановления при сбоях или случайном удалении;
   
         * Переход на использование terraform для управления ресурсами, созданными через `UI` или `YC CLI`;
   
   ___
   









