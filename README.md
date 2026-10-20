# Spotifice: servicios en Python con ZeroC Ice

**ES** · [EN](#english)

Servicios de un sistema distribuido de streaming musical, hechos en **Python con ZeroC Ice**. Proyecto de la asignatura de Sistemas Distribuidos (UCLM, curso 2025/2026).

## Qué incluye

- `media_server.py`: servidor de medios con biblioteca, listas de reproducción, autenticación con hash y sal, y envío de audio por fragmentos.
- `media_render.py`: reproductor de medios con control de reproducción (reproducir, pausar, siguiente, anterior y repetición).
- `media_directory.py`: directorio de servicios con descubrimiento dinámico mediante publicación y suscripción en **IceStorm**.
- `media_control.py`: cliente de control.

El despliegue de la aplicación con **IceGrid** sobre dos máquinas está en otro repositorio: [IceGrid](https://github.com/marcosgr5/IceGrid).

## Qué no incluye

La interfaz Ice (`spotifice_v3.ice`), el reproductor de GStreamer, los tests y el material de partida son de los profesores de la asignatura y no se publican aquí. Por eso este repositorio sirve para **leer el código**, pero no se puede ejecutar por sí solo.

## Créditos

Autor: **Marcos Galán Rodríguez**.

---

## English

Services of a distributed music-streaming system built with **Python and ZeroC Ice**. Project for the Distributed Systems course (UCLM, Spain, 2025/2026).

### Features

- `media_server.py`: media server with library, playlists, salted-hash authentication and chunked audio streaming.
- `media_render.py`: media renderer with playback control (play, pause, next, previous and repeat).
- `media_directory.py`: service directory with dynamic discovery through **IceStorm** publish/subscribe.
- `media_control.py`: control client.

Deployment with **IceGrid** across two machines lives in a separate repository: [IceGrid](https://github.com/marcosgr5/IceGrid).

### What is not included

The Ice interface (`spotifice_v3.ice`), the GStreamer player, the tests and the starter material belong to the course instructors and are not published here. This repository is meant for **reading the code**; it cannot run on its own.

### Credits

Author: **Marcos Galán Rodríguez**.
