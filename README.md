# POKEMON

## remarques de M. Luttringer

c'est possible de créer un unique controlleur qui implémente dans des threads séparés les fonctionnalités du méta-controleur et des controlleurs liés à chaque switch

## run the system

```bash
./run.sh
```

You can create a random topology using 

```bash
python topology_generator.py --output_name 40-switches.json --topo random -n 40 -d 4
```

(it creates a random topology with 40 switches and an average degree of 4)

and then start it with :

```bash
sudo p4run --config 40-switches.json
```

In another terminal attach to the container to run the controller,

```bash
docker exec -it p4 bash
```

```bash
python3 routing-controller.py
```