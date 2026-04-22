#!/usr/bin/env python3

import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

# ----------------------------------------------------------------------
# Configuración del alumno
# ----------------------------------------------------------------------
STUDENT_NAME = "César Montoya Caballero"
MATRICULA = "AL02992400"
REGION = "us-east-1"


# ----------------------------------------------------------------------
# Funciones auxiliares para obtener metadatos de la instancia actual
# ----------------------------------------------------------------------
def get_instance_id():
    """Obtiene el ID de la instancia actual mediante IMDSv2."""
    # Obtener token
    token_url = "http://169.254.169.254/latest/api/token"
    headers = {"X-aws-ec2-metadata-token-ttl-seconds": "21600"}
    try:
        response = requests.put(token_url, headers=headers, timeout=2)
        response.raise_for_status()
        token = response.text
    except Exception as e:
        print(f"❌ Error obteniendo token IMDS: {e}")
        sys.exit(1)

    # Consultar instance-id
    metadata_url = "http://169.254.169.254/latest/meta-data/instance-id"
    headers = {"X-aws-ec2-metadata-token": token}
    try:
        response = requests.get(metadata_url, headers=headers, timeout=2)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Error obteniendo instance-id: {e}")
        sys.exit(1)


def get_environment_from_tags(ec2_client, instance_id):
    """
    Lee las tags de la instancia actual y devuelve el valor de la tag 'Environment'.
    Si no existe, pregunta al usuario.
    """
    try:
        response = ec2_client.describe_tags(
            Filters=[
                {"Name": "resource-id", "Values": [instance_id]},
                {"Name": "key", "Values": ["Environment"]},
            ]
        )
        tags = response.get("Tags", [])
        if tags:
            return tags[0]["Value"]
        else:
            print("⚠️  La instancia actual no tiene la tag 'Environment'.")
            # Fallback: pregunta manual
            env = input(
                "Ingrese el ambiente manualmente (Development/Production): "
            ).strip()
            if env not in ["Development", "Production"]:
                print("❌ Ambiente inválido. Saliendo.")
                sys.exit(1)
            return env
    except ClientError as e:
        print(f"❌ Error leyendo tags: {e}")
        sys.exit(1)


def get_instances_by_environment(ec2_client, environment):
    """
    Retorna una lista de instancias que poseen la tag Environment = 'environment'.
    Cada elemento es un dict con información relevante.
    """
    filters = [
        {"Name": "tag:Environment", "Values": [environment]},
        {
            "Name": "instance-state-name",
            "Values": ["pending", "running", "stopping", "stopped"],
        },
    ]
    try:
        response = ec2_client.describe_instances(Filters=filters)
        instances = []
        for reservation in response["Reservations"]:
            for inst in reservation["Instances"]:
                # Extraer nombre desde tags
                name = "N/A"
                for tag in inst.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break
                instances.append(
                    {
                        "id": inst["InstanceId"],
                        "name": name,
                        "state": inst["State"]["Name"],
                        "private_ip": inst.get("PrivateIpAddress", "N/A"),
                        "public_ip": inst.get("PublicIpAddress", "N/A"),
                    }
                )
        return instances
    except ClientError as e:
        print(f"❌ Error describiendo instancias: {e}")
        return []


def print_instances_table(instances):
    """Muestra en formato tabla las instancias."""
    if not instances:
        print("📭 No se encontraron instancias en este ambiente.")
        return
    print(
        "\n{:<20} {:<20} {:<12} {:<16} {:<16}".format(
            "Nombre", "ID", "Estado", "IP Privada", "IP Pública"
        )
    )
    print("-" * 90)
    for inst in instances:
        print(
            "{:<20} {:<20} {:<12} {:<16} {:<16}".format(
                inst["name"][:20],
                inst["id"],
                inst["state"],
                inst["private_ip"],
                inst["public_ip"] if inst["public_ip"] != "N/A" else "N/A",
            )
        )
    print()


def select_instance(instances, action):
    """Muestra lista numerada y pide al usuario seleccionar una instancia."""
    if not instances:
        print("⚠️  No hay instancias disponibles para {action}.")
        return None
    print(f"\nSeleccione la instancia a {action}:")
    for idx, inst in enumerate(instances, start=1):
        print(f"{idx}. {inst['name']} ({inst['id']}) - Estado: {inst['state']}")
    try:
        choice = int(input("Número: "))
        if 1 <= choice <= len(instances):
            return instances[choice - 1]["id"]
        else:
            print("❌ Número fuera de rango.")
            return None
    except ValueError:
        print("❌ Entrada inválida.")
        return None


def execute_action(ec2_client, instance_ids, action):
    """Ejecuta start/stop/reboot sobre una lista de instance_ids."""
    if not instance_ids:
        return
    try:
        if action == "start":
            response = ec2_client.start_instances(InstanceIds=instance_ids)
            print(f"🟢 Iniciando instancia(s): {instance_ids}")
        elif action == "stop":
            response = ec2_client.stop_instances(InstanceIds=instance_ids)
            print(f"🔴 Deteniendo instancia(s): {instance_ids}")
        elif action == "reboot":
            response = ec2_client.reboot_instances(InstanceIds=instance_ids)
            print(f"🔄 Reiniciando instancia(s): {instance_ids}")
        else:
            return
        # Espera breve para actualizar estado
        time.sleep(2)
        print("✅ Operación enviada correctamente.")
    except ClientError as e:
        print(f"❌ Error al {action}: {e}")


def main():
    # Inicializar cliente EC2
    ec2_client = boto3.client("ec2", region_name=REGION)

    # Detectar ambiente actual
    print("🔍 Detectando ambiente...")
    instance_id = get_instance_id()
    environment = get_environment_from_tags(ec2_client, instance_id)

    # Mostrar encabezado permanente
    env_display = "Desarrollo" if environment == "Development" else "Producción"

    while True:
        # Limpiar pantalla (opcional, para mejor UX)
        # print("\033c", end="")   # descomentar si se desea limpiar
        print("=" * 50)
        print(f"Alumno: {STUDENT_NAME}")
        print(f"Matrícula: {MATRICULA}")
        print(f"Ambiente: {env_display}")
        print("=" * 50)
        print("1. Listar instancias")
        print("2. Iniciar instancia")
        print("3. Detener instancia")
        print("4. Reiniciar instancia")
        print("5. Salir")
        print("=" * 50)
        opcion = input("Seleccione una opción: ").strip()

        if opcion == "1":
            instancias = get_instances_by_environment(ec2_client, environment)
            print_instances_table(instancias)
            input("Presione Enter para continuar...")
        elif opcion == "2":
            instancias = get_instances_by_environment(ec2_client, environment)
            # Filtrar instancias que no estén ya en 'running' (opcional)
            instancias_start = [i for i in instancias if i["state"] != "running"]
            if not instancias_start:
                print("✅ Todas las instancias ya están en estado 'running'.")
                input("Presione Enter para continuar...")
                continue
            inst_id = select_instance(instancias_start, "iniciar")
            if inst_id:
                execute_action(ec2_client, [inst_id], "start")
            input("Presione Enter para continuar...")
        elif opcion == "3":
            instancias = get_instances_by_environment(ec2_client, environment)
            # Filtrar instancias que no estén ya en 'stopped'
            instancias_stop = [i for i in instancias if i["state"] != "stopped"]
            if not instancias_stop:
                print("✅ Todas las instancias ya están detenidas.")
                input("Presione Enter para continuar...")
                continue
            inst_id = select_instance(instancias_stop, "detener")
            if inst_id:
                execute_action(ec2_client, [inst_id], "stop")
            input("Presione Enter para continuar...")
        elif opcion == "4":
            instancias = get_instances_by_environment(ec2_client, environment)
            # Solo se puede reiniciar instancias en estado 'running'
            instancias_reboot = [i for i in instancias if i["state"] == "running"]
            if not instancias_reboot:
                print("⚠️  No hay instancias en estado 'running' para reiniciar.")
                input("Presione Enter para continuar...")
                continue
            inst_id = select_instance(instancias_reboot, "reiniciar")
            if inst_id:
                execute_action(ec2_client, [inst_id], "reboot")
            input("Presione Enter para continuar...")
        elif opcion == "5":
            print("👋 Saliendo del programa.")
            break
        else:
            print("❌ Opción no válida. Intente de nuevo.")
            input("Presione Enter para continuar...")


if __name__ == "__main__":
    main()
