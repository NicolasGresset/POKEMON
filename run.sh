#!/bin/bash

sudo docker run -v $PWD/src:/home --rm --name p4 -it --privileged registry.app.unistra.fr/jr.luttringer/reseaux-programmables-conteneur/p4-utils bash
