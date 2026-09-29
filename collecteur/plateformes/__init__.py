"""Un module par plateforme. Chacun expose collecter(club, jours, client) -> list[Creneau]."""

from . import anybuddy, bigcaptain, doinsport, matchi, playtomic, sportfinder

PLATEFORMES = {
    "doinsport": doinsport,
    "playtomic": playtomic,
    "sportfinder": sportfinder,
    "anybuddy": anybuddy,
    "matchi": matchi,
    "bigcaptain": bigcaptain,
}
