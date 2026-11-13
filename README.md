<p align="center"><img src="assets/icon.svg" width="144" alt="Fil Pilote Thermostat"></p>

# Fil Pilote Thermostat

[Français](README.md) · [English](README.en.md) · [Русский](README.ru.md)

Un thermostat local pour Home Assistant : pilotez vos radiateurs électriques avec une **interface fil pilote à deux relais** et une sonde de température ambiante. Configuration depuis l’interface HA ou en YAML.

**Home Assistant 2026.11 minimum.** Les tests utilisent Core 2026.11.1 et Python 3.14. Interface de configuration disponible en français, anglais et russe, selon la langue de votre profil HA.

## Installation

**Aucune configuration YAML n’est nécessaire.** La méthode recommandée est la configuration depuis l’interface Home Assistant : vous pouvez y sélectionner les relais et la sonde, puis modifier les paramètres sans éditer `configuration.yaml`.

1. Copiez le dossier `custom_components/fil_pilote_thermostat` dans le répertoire de configuration HA : `/config/custom_components/fil_pilote_thermostat/`.
2. Redémarrez Home Assistant.
3. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration → Fil Pilote Thermostat**.
4. Sélectionnez les relais S1 et S2, puis la sonde de température. Réglez les limites et les tolérances.

Les relais peuvent être des entités `switch`, `light` ou `input_boolean` à commande marche/arrêt. La sonde doit être une entité `sensor`. Les options sont modifiables sans redémarrer HA. Les relais restent fixes : recréez l’intégration pour les changer. Un relais ne peut pas être partagé entre plusieurs thermostats configurés dans l’interface.

Le projet est disponible sur [GitHub](https://github.com/dmitry-pervushin/fil-pilote-thermostat). Pour l’ajouter dans HACS, ouvrez **Dépôts personnalisés**, saisissez l’URL de ce dépôt et choisissez la catégorie **Intégration**. Le projet n’est pas référencé dans le catalogue HACS par défaut.

## Ordres fil pilote

La convention des relais du composant d’origine est conservée :

| Préréglage HA | Ordre radiateur | S1 | S2 |
| --- | --- | --- | --- |
| `comfort` | Confort | off | off |
| `eco` | Éco | on | on |
| `away` | Hors-gel | on | off |
| `sleep` | Arrêt | off | on |

**S1 et S2 ne sont pas interchangeables.** Vérifiez cette table avec votre interface fil pilote avant d’activer le chauffage. Il s’agit des états logiques des relais, pas d’un schéma de câblage secteur. Le composant suppose une interface fil pilote appropriée, déjà installée.

En mode HVAC `heat`, Confort et Éco utilisent la sonde externe avec hystérésis : demande de chauffe à `consigne − cold_tolerance`, arrêt à `consigne + hot_tolerance`. Entre ces seuils, la demande précédente est conservée. En Éco, le radiateur peut également appliquer sa propre réduction de température.

Hors-gel envoie cet ordre en continu : le seuil antigel reste géré par le radiateur. Arrêt envoie l’ordre d’arrêt en continu. Le mode HVAC `off` demande toujours l’arrêt, même sans sonde valide. Choisir un préréglage n’active pas le chauffage. À la première installation, les valeurs par défaut sont **Off**, **Hors-gel** et **20 °C**, dans les limites configurées.

Le radiateur doit être en mode externe/programmation/fil pilote et son thermostat local doit autoriser la température souhaitée. Le signal fil pilote ne contourne pas sa limite interne. `hvac_action: heating` indique un ordre Confort/Éco observé, pas une mesure de puissance ni la preuve que la résistance chauffe.

## Températures et redémarrage

Les valeurs de configuration et les tolérances sont en **°C**. HA convertit l’affichage de l’entité climate et les actions standard dans les unités de votre système. Les sondes en °C, °F ou K sont converties en °C ; une sonde sans unité est interprétée en °C.

La consigne, le mode HVAC et le préréglage sont restaurés après un redémarrage ou un rechargement. Les champs facultatifs `target_temp`, `initial_hvac_mode` et `initial_preset` **remplacent les valeurs restaurées à chaque démarrage/rechargement**. Laissez-les vides pour conserver les derniers réglages de l’utilisateur. Les modes restaurés invalides sont ignorés ; une consigne invalide ou hors limites est remplacée par une valeur par défaut valide.

## Gestion des défauts

Une sonde absente, indisponible, non numérique, NaN ou infinie rend le thermostat indisponible et déclenche une demande d’arrêt. Un relais manquant produit le même effet ; le composant tente toujours d’appliquer la combinaison d’arrêt sur les relais accessibles. Si un relais est inaccessible ou défectueux, l’ordre d’arrêt complet ne peut pas être garanti.

`sensor_timeout` permet de refuser une mesure trop ancienne, en secondes depuis le dernier rapport de la sonde. La valeur `0` désactive cette fonction et convient aux sondes qui ne publient qu’en cas de changement. La vérification a lieu lors des changements d’état et toutes les 60 secondes : la détection d’expiration peut donc prendre une minute supplémentaire.

Les commandes attendent la fin des actions de relais, évitent les appels redondants et sont sérialisées. Les échecs et les écarts d’état sont revérifiés toutes les 60 secondes. Un changement de relais déclenche aussi une correction : utilisez l’entité climate pour contrôler le chauffage. Une erreur de commande rend le thermostat indisponible jusqu’à une réconciliation réussie. Le déchargement supprime les abonnements et les temporisateurs ; il laisse le dernier signal physique inchangé.

Attributs de diagnostic : `pilot_mode`, `requested_pilot_mode`, `requested_hvac_mode`, `requested_preset_mode`, `heater_s1`, `heater_s2`, `sensor_entity_id`, `command_failed`. HA masque les attributs d’état d’une entité indisponible ; le téléchargement des diagnostics de l’intégration reste disponible, y compris pendant une panne.

## Configuration YAML (facultative)

Cette section est une alternative à la configuration depuis l’interface, conservée pour les installations existantes et les utilisateurs qui préfèrent le YAML. Si vous avez ajouté le thermostat depuis l’interface, ignorez cette section : aucun bloc YAML n’est à ajouter.

Les noms d’options existants restent pris en charge. Ne configurez pas les mêmes relais à la fois dans le YAML et dans l’interface. Pour migrer, retirez l’ancien thermostat YAML et redémarrez HA avant de créer l’intégration dans l’interface ; adaptez au besoin les identifiants dans vos tableaux de bord et automatisations.

Si votre ancienne configuration utilisait des valeurs en °F, convertissez les consignes, les limites et les tolérances en °C avant la mise à jour. Le nouveau format de configuration utilise toujours les °C.

```yaml
climate:
  - platform: fil_pilote_thermostat
    name: Salon
    unique_id: salon_fil_pilote
    heater_s1: switch.radiateur_s1
    heater_s2: switch.radiateur_s2
    target_sensor: sensor.temperature_salon
    min_temp: 7
    max_temp: 30
    cold_tolerance: 0.3
    hot_tolerance: 0.3
    precision: 0.1
    sensor_timeout: 0
    # Facultatif : remplace les réglages restaurés à chaque démarrage.
    # target_temp: 20
    # initial_hvac_mode: heat
    # initial_preset: comfort
```

| Option | Défaut | Description |
| --- | --- | --- |
| `heater_s1`, `heater_s2` | obligatoire | Deux relais distincts |
| `target_sensor` | obligatoire | Sonde de température ambiante |
| `name` | Fil Pilote Thermostat | Nom de l’entité |
| `unique_id` | facultatif | Permet la gestion de l’entité YAML dans le registre |
| `min_temp`, `max_temp` | 7 / 35 | Limites en °C ; minimum strictement inférieur au maximum |
| `cold_tolerance`, `hot_tolerance` | 0.3 / 0.3 | Hystérésis en °C ; valeurs positives ou nulles, au moins une strictement positive |
| `precision` | 0.1 | Précision et pas : 0.1, 0.5 ou 1 |
| `sensor_timeout` | 0 | Âge maximal du dernier rapport en secondes ; 0 désactive |
| `target_temp` | restaurée / 20 | Consigne initiale en °C |
| `initial_hvac_mode` | restauré / off | `heat` ou `off` |
| `initial_preset` | restauré / away | `comfort`, `eco`, `away` ou `sleep` |
