# Lossy routeur

On utilise l'extern random pour tirer une valeur entre 1 et 100 et on affecte le port de sortie à 511 pour indiquer à l'ingress de drop le paquet, comme suggéré dans la [doc de BMv2](https://github.com/nsg-ethz/p4-learning/wiki/BMv2-Simple-Switch#standard-metadata)


Avec une topologie simple, on vérifie avec des pings successifs que des paquets se font bien drops. On observe un taux de packet loss de 35% pour 17 paquets, ce qui confirme la correction du programme.

```bash
mininet> h1 ping h2
PING 10.0.0.2 (10.0.0.2) 56(84) bytes of data.
64 bytes from 10.0.0.2: icmp_seq=3 ttl=63 time=1.84 ms
64 bytes from 10.0.0.2: icmp_seq=4 ttl=63 time=1.81 ms
64 bytes from 10.0.0.2: icmp_seq=5 ttl=63 time=2.03 ms
64 bytes from 10.0.0.2: icmp_seq=7 ttl=63 time=2.02 ms
64 bytes from 10.0.0.2: icmp_seq=8 ttl=63 time=1.79 ms
64 bytes from 10.0.0.2: icmp_seq=9 ttl=63 time=2.27 ms
64 bytes from 10.0.0.2: icmp_seq=10 ttl=63 time=2.05 ms
64 bytes from 10.0.0.2: icmp_seq=11 ttl=63 time=2.10 ms
64 bytes from 10.0.0.2: icmp_seq=13 ttl=63 time=2.06 ms
64 bytes from 10.0.0.2: icmp_seq=14 ttl=63 time=1.96 ms
64 bytes from 10.0.0.2: icmp_seq=17 ttl=63 time=1.78 ms
^C
--- 10.0.0.2 ping statistics ---
17 packets transmitted, 11 received, 35.2941% packet loss, time 16112ms
rtt min/avg/max/mdev = 1.776/1.972/2.266/0.146 ms
```

