# POKEMON

Ce [repository](https://github.com/NicolasGresset/POKEMON) contient le code pour le projet POKEMON de Nicolas Gresset-Bourgeois et Matthieu Ferreira--Rivier. Il contient aussi le [rendu au format pdf](./rendu.pdf).

## Structure

```
└── src
    ├── controllers : les différents contrôleurs Python utilisés
    ├── helper      : des helpers pour générer des topologies
    ├── log         : dossier contenant les logs des switchs p4
    ├── p4src       : fichier sources p4
    ├── pcap        : enregistrements pcap des switchs p4
    └── topos       : topologies utilisées pour les tests
```

## Lancer un scénario de test

```bash
./run.sh
cd home/src
```

Toutes les topologies sont présentes dans `src/topos`


```bash
sudo p4run --config topos/stupid_router_test.json
```

Dans un autre terminal, récupérer une session bash au conteneur pour lancer le contrôleur

```bash
docker exec -it p4 bash
cd home/src
python3 controllers/meta_controller.py topos/stupid_router_test.json
```

Il FAUT passer la même topologie en paramètre au méta-contrôleur.

Le méta-contrôleur lance automatiquement tous les contrôleurs de chaque switch.