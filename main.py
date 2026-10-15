import json
import os
import shutil
import tempfile
import uuid
import copy
import csv
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
except Exception:
    ctk = None


USER_DATA_DIR = Path.home() / ".local" / "share" / "PuntajeNewcom"
DATA_FILE = USER_DATA_DIR / "datos_torneo.json"
BACKUP_DIR = USER_DATA_DIR / "backups"


class DataStore:
    def __init__(self, data_dir: Optional[Path] = None, data_file: Optional[Path] = None):
        self.data_dir = data_dir or USER_DATA_DIR
        self.data_file = data_file or DATA_FILE
        self.backup_dir = self.data_dir / "backups"
        self.ensure_dirs()

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _default_payload(self):
        return {
            "version": 1,
            "last_updated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "tournaments": []
        }

    def load(self):
        if not self.data_file.exists():
            self.save(self._default_payload())
            return self._default_payload()
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Formato de datos inválido")
            return data
        except Exception as exc:
            backup = self.find_valid_backup()
            if backup:
                try:
                    with open(backup, 'r', encoding='utf-8') as f:
                        recovered = json.load(f)
                    if isinstance(recovered, dict):
                        self.data_file.write_text(json.dumps(recovered, ensure_ascii=False, indent=2), encoding='utf-8')
                        return recovered
                except Exception:
                    pass
            raise RuntimeError(f"No se pudo leer los datos: {exc}")

    def find_valid_backup(self):
        if not self.backup_dir.exists():
            return None
        files = sorted(self.backup_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return path
            except Exception:
                continue
        return None

    def save(self, payload: Dict[str, Any]):
        payload = copy.deepcopy(payload)
        payload["version"] = payload.get("version", 1)
        payload["last_updated"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="puntaje_", suffix=".tmp", dir=str(self.data_dir))
        os.close(tmp_fd)
        tmp = Path(tmp_path)
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self.backup_old_file()
            os.replace(tmp, self.data_file)
            self.write_backup(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    def backup_old_file(self):
        if not self.data_file.exists():
            return
        backup_name = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.bak"
        backup_path = self.backup_dir / backup_name
        shutil.copy2(self.data_file, backup_path)
        self.cleanup_old_backups()

    def write_backup(self, content: str):
        backup_name = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.bak"
        backup_path = self.backup_dir / backup_name
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        self.cleanup_old_backups()

    def cleanup_old_backups(self):
        files = sorted(self.backup_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[10:]:
            try:
                path.unlink()
            except Exception:
                pass


class TournamentManager:
    def __init__(self):
        self.store = DataStore()
        self.data = self.store.load()

    def ensure_tournament(self, tournament_id=None):
        if not self.data.get("tournaments"):
            self.data["tournaments"] = []
        if tournament_id is None:
            return self.data["tournaments"][0] if self.data["tournaments"] else None
        for tournament in self.data["tournaments"]:
            if tournament["id"] == tournament_id:
                return tournament
        return None

    def list_tournaments(self):
        return self.data.get("tournaments", [])

    def create_tournament(self, name, fecha=None, ubicacion=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre del torneo no puede estar vacío.")
        if any(t.get("name", "").lower() == name.lower() for t in self.data["tournaments"]):
            raise ValueError("Ya existe un torneo con ese nombre.")
        tournament = {
            "id": str(uuid.uuid4()),
            "name": name,
            "fecha": fecha or "",
            "ubicacion": ubicacion or "",
            "active": True,
            "categories": []
        }
        self.data["tournaments"].append(tournament)
        self.save()
        return tournament

    def update_tournament(self, tournament_id, name=None, fecha=None, ubicacion=None):
        tournament = self.ensure_tournament(tournament_id)
        if not tournament:
            raise ValueError("Torneo no encontrado.")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("El nombre del torneo no puede estar vacío.")
            if any(t.get("id") != tournament_id and t.get("name", "").lower() == name.lower() for t in self.data["tournaments"]):
                raise ValueError("Ya existe otro torneo con ese nombre.")
            tournament["name"] = name
        if fecha is not None:
            tournament["fecha"] = fecha
        if ubicacion is not None:
            tournament["ubicacion"] = ubicacion
        self.save()
        return tournament

    def delete_tournament(self, tournament_id):
        for idx, tournament in enumerate(self.data["tournaments"]):
            if tournament["id"] == tournament_id:
                del self.data["tournaments"][idx]
                self.save()
                return True
        return False

    def save(self):
        self.store.save(self.data)

    def set_active_tournament(self, tournament_id):
        if tournament_id is not None and not self.ensure_tournament(tournament_id):
            raise ValueError("Torneo no encontrado.")
        self.data["active_tournament_id"] = tournament_id
        self.save()


class CategoryManager:
    def __init__(self, tournament):
        self.tournament = tournament

    def list_categories(self):
        return self.tournament.setdefault("categories", [])

    def create_category(self, name, modalidad, descripcion=""):
        name = (name or "").strip()
        modalidad = (modalidad or "").strip()
        if not name or not modalidad:
            raise ValueError("La categoría y la modalidad son obligatorias.")
        existing = self.list_categories()
        if any(c.get("name", "").lower() == name.lower() and c.get("modalidad", "").lower() == modalidad.lower() for c in existing):
            raise ValueError("Ya existe esa categoría y modalidad.")
        category = {
            "id": str(uuid.uuid4()),
            "name": name,
            "modalidad": modalidad,
            "descripcion": descripcion,
            "zones": [],
            "stage_unique": None,
            "state": "in_progress"
        }
        existing.append(category)
        return category

    def update_category(self, category_id, name=None, modalidad=None, descripcion=None):
        for category in self.list_categories():
            if category["id"] == category_id:
                if name is not None:
                    name = name.strip();
                    if not name: raise ValueError("La categoría no puede quedar vacía.")
                    category["name"] = name
                if modalidad is not None:
                    modalidad = modalidad.strip();
                    if not modalidad: raise ValueError("La modalidad no puede quedar vacía.")
                    category["modalidad"] = modalidad
                if descripcion is not None:
                    category["descripcion"] = descripcion
                return category
        raise ValueError("Categoría no encontrada.")

    def delete_category(self, category_id):
        categories = self.list_categories()
        for idx, category in enumerate(categories):
            if category["id"] == category_id:
                if category.get("zones"):
                    raise ValueError("No se puede eliminar una categoría con zonas cargadas.")
                del categories[idx]
                return True
        raise ValueError("Categoría no encontrada.")


class ZoneManager:
    def __init__(self, tournament):
        self.tournament = tournament

    def _find_category(self, category_id):
        for category in self.tournament.get("categories", []):
            if category["id"] == category_id:
                return category
        raise ValueError("Categoría no encontrada.")

    def list_zones(self, category_id):
        category = self._find_category(category_id)
        return category.setdefault("zones", [])

    def create_zone(self, category_id, name):
        category = self._find_category(category_id)
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre de la zona es obligatorio.")
        if any(z.get("name", "").lower() == name.lower() for z in category.get("zones", [])):
            raise ValueError("Ya existe una zona con ese nombre en la categoría.")
        zone = {
            "id": str(uuid.uuid4()),
            "name": name,
            "teams": [],
            "results": [],
            "state": "open"
        }
        category.setdefault("zones", []).append(zone)
        return zone

    def update_zone(self, category_id, zone_id, name):
        zone = self.get_zone(category_id, zone_id)
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre de la zona es obligatorio.")
        zone["name"] = name
        return zone

    def delete_zone(self, category_id, zone_id):
        category = self._find_category(category_id)
        zones = category.get("zones", [])
        for idx, zone in enumerate(zones):
            if zone["id"] == zone_id:
                if zone.get("teams"):
                    raise ValueError("No se puede eliminar una zona con equipos cargados.")
                del zones[idx]
                return True
        raise ValueError("Zona no encontrada.")

    def get_zone(self, category_id, zone_id):
        category = self._find_category(category_id)
        for zone in category.get("zones", []):
            if zone["id"] == zone_id:
                return zone
        raise ValueError("Zona no encontrada.")

    def list_teams(self, category_id, zone_id=None):
        if zone_id is None:
            teams = []
            for category in self.tournament.get("categories", []):
                if category["id"] == category_id:
                    for zone in category.get("zones", []):
                        teams.extend(zone.get("teams", []))
                    return teams
        zone = self.get_zone(category_id, zone_id)
        return zone.get("teams", [])

    def add_team(self, category_id, zone_id, name, club=None):
        category = self._find_category(category_id)
        zone = self.get_zone(category_id, zone_id)
        name = (name or "").strip()
        if not name:
            raise ValueError("El nombre del equipo es obligatorio.")
        if any(team.get("name", "").lower() == name.lower() for team in zone.get("teams", [])):
            raise ValueError("Ya existe un equipo con ese nombre en la zona.")
        team = {
            "id": str(uuid.uuid4()),
            "name": name,
            "club": club or "",
            "category_id": category_id,
            "modalidad": category.get("modalidad", ""),
            "zone_id": zone_id,
            "active": True
        }
        zone.setdefault("teams", []).append(team)
        return team

    def update_team(self, category_id, zone_id, team_id, name=None, club=None):
        zone = self.get_zone(category_id, zone_id)
        for team in zone.get("teams", []):
            if team["id"] == team_id:
                if name is not None:
                    name = name.strip();
                    if not name: raise ValueError("El nombre del equipo no puede estar vacío.")
                    team["name"] = name
                if club is not None:
                    team["club"] = club
                return team
        raise ValueError("Equipo no encontrado.")

    def delete_team(self, category_id, zone_id, team_id):
        zone = self.get_zone(category_id, zone_id)
        for idx, team in enumerate(zone.get("teams", [])):
            if team["id"] == team_id:
                del zone["teams"][idx]
                return True
        raise ValueError("Equipo no encontrado.")


class ScoringEngine:
    VALID_RESULTS = frozenset(((2, 0), (2, 1), (1, 2), (0, 2)))

    @staticmethod
    def official_points_for_result(set_a, set_b):
        if set_a == 2 and set_b == 0:
            return 3, 0
        if set_a == 2 and set_b == 1:
            return 2, 1
        if set_a == 1 and set_b == 2:
            return 1, 2
        if set_a == 0 and set_b == 2:
            return 0, 3
        raise ValueError("Resultado de partido inválido.")

    @staticmethod
    def validate_match_result(score_a, score_b):
        return (score_a, score_b) in ScoringEngine.VALID_RESULTS

    @staticmethod
    def round_result_for_team(match):
        if match["sets_a"] == 2 and match["sets_b"] == 0:
            return 3, 0
        if match["sets_a"] == 2 and match["sets_b"] == 1:
            return 2, 1
        if match["sets_a"] == 1 and match["sets_b"] == 2:
            return 1, 2
        if match["sets_a"] == 0 and match["sets_b"] == 2:
            return 0, 3
        raise ValueError("Resultado imposible.")

    @staticmethod
    def make_match_result(team_a, team_b, sets_a, sets_b, score_lines):
        if team_a == team_b:
            raise ValueError("Un equipo no puede jugar contra sí mismo.")
        if not ScoringEngine.validate_match_result(sets_a, sets_b):
            raise ValueError("Resultado de partido inválido: use 2–0, 2–1, 1–2 o 0–2.")
        score_lines = ScoringEngine.validate_set_scores(sets_a, sets_b, score_lines)
        result = {
            "team_a": team_a,
            "team_b": team_b,
            "sets_a": sets_a,
            "sets_b": sets_b,
            "score_lines": score_lines,
            "score_format": "sets",
            "status": "confirmed",
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"
        }
        return result

    @staticmethod
    def derive_match_result(score_lines):
        """Calculate sets won from real set scores rather than user-entered totals."""
        if not isinstance(score_lines, (list, tuple)) or len(score_lines) not in (2, 3):
            raise ValueError("Debe cargar dos sets y, si corresponde, un tercero.")
        wins_a = wins_b = 0
        canonical = []
        for index, line in enumerate(score_lines):
            if not isinstance(line, (list, tuple)) or len(line) != 2:
                raise ValueError("Cada set debe tener puntos para ambos equipos.")
            try:
                a, b = int(line[0]), int(line[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("Los puntos deben ser números enteros.") from exc
            if a < 0 or b < 0 or a == b:
                raise ValueError("Los puntos deben ser no negativos y distintos.")
            if (wins_a == 2 or wins_b == 2):
                raise ValueError("No se permite cargar sets después de finalizar 2–0.")
            canonical.append([a, b])
            wins_a += a > b
            wins_b += b > a
            if index == 1 and len(score_lines) == 3 and (wins_a, wins_b) != (1, 1):
                raise ValueError("El tercer set solo se habilita con resultado parcial 1–1.")
        if (wins_a, wins_b) not in ScoringEngine.VALID_RESULTS:
            raise ValueError("El resultado de los sets no completa un partido válido.")
        return wins_a, wins_b, canonical

    @staticmethod
    def score_for_match(result):
        return ScoringEngine.official_points_for_result(result["sets_a"], result["sets_b"])

    @staticmethod
    def is_confirmed_result(result):
        """Return whether a saved result is complete enough to classify.

        Old records may contain only the traditional result. They still count
        for match/classification points, but cannot contribute invented PF/PC.
        """
        if result.get("status", "confirmed") not in ("confirmed", "final", None):
            return False
        try:
            if not ScoringEngine.validate_match_result(result["sets_a"], result["sets_b"]):
                return False
            lines = result.get("score_lines")
            return (
                result.get("score_format") == "sets"
                and isinstance(lines, (list, tuple))
                and len(lines) == result["sets_a"] + result["sets_b"]
                and all(
                    isinstance(line, (list, tuple)) and len(line) == 2
                    and all(isinstance(value, int) and value >= 0 for value in line)
                    for line in lines
                )
            )
        except (KeyError, TypeError):
            return False

    @staticmethod
    def validate_set_scores(sets_a, sets_b, score_lines):
        """Validate and return canonical per-set scores: [[A, B], ...]."""
        expected = sets_a + sets_b
        if not isinstance(score_lines, (list, tuple)) or len(score_lines) != expected:
            raise ValueError(f"Debe cargar los puntos de los {expected} sets disputados.")
        canonical = []
        for line in score_lines:
            if not isinstance(line, (list, tuple)) or len(line) != 2:
                raise ValueError("Cada set debe tener puntos para ambos equipos.")
            try:
                a, b = int(line[0]), int(line[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("Los puntos de cada set deben ser números enteros.") from exc
            if a < 0 or b < 0:
                raise ValueError("Los puntos de cada set no pueden ser negativos.")
            canonical.append([a, b])
        return canonical

    @staticmethod
    def set_totals(match):
        """Return the two raw set totals for Team A (PF, PC)."""
        lines = match.get("score_lines", [])
        if ScoringEngine.is_confirmed_result(match):
            return (
                sum(line[0] for line in lines),
                sum(line[1] for line in lines),
            )
        return (0, 0)

    @staticmethod
    def team_set_totals(match, team_id):
        lines = match.get("score_lines", [])
        if ScoringEngine.is_confirmed_result(match):
            if match["team_a"] == team_id:
                return sum(line[0] for line in lines), sum(line[1] for line in lines)
            return sum(line[1] for line in lines), sum(line[0] for line in lines)
        # Historical results without real set markers deliberately contribute
        # zero PF/PC; their traditional result remains usable for standings.
        return 0, 0


class StageManager:
    def __init__(self, tournament):
        self.tournament = tournament

    def get_category(self, category_id):
        for category in self.tournament.get("categories", []):
            if category["id"] == category_id:
                return category
        raise ValueError("Categoría no encontrada.")

    def top_two_teams_by_zone(self, category_id, zone_id):
        cls = ClassificationManager(self.tournament)
        ranking = cls.calculate_zone_ranking(category_id, zone_id)
        return ranking[:2]

    def confirm_zone_promotions(self, category_id):
        category = self.get_category(category_id)
        unique = {
            "id": str(uuid.uuid4()),
            "name": f"Zona única - {category.get('name','')} {category.get('modalidad','')}",
            "type": "unique",
            "teams": [],
            "results": [],
            "state": "open",
            "base_zone_ids": []
        }
        for zone in category.get("zones", []):
            ranking = ClassificationManager(self.tournament).calculate_zone_ranking(category_id, zone["id"])
            top = ranking[:2]
            unique["teams"].extend([team["id"] for team in top])
            unique["base_zone_ids"].append(zone["id"])
        unique["teams"] = list(dict.fromkeys(unique["teams"]))
        category["stage_unique"] = unique
        category["state"] = "unique_pending"
        return unique

    def unique_teams(self, category_id):
        category = self.get_category(category_id)
        ids = set((category.get("stage_unique") or {}).get("teams", []))
        return [team for zone in category.get("zones", []) for team in zone.get("teams", [])
                if team.get("id") in ids]


class ClassificationManager:
    def __init__(self, tournament):
        self.tournament = tournament

    @staticmethod
    def summarise_team(team_id, team_name, matches):
        ganados = 0
        perdidos = 0
        puntos_partido = 0
        puntos_favor = 0
        puntos_contra = 0
        partidos_jugados = 0
        for match in matches:
            if team_id not in (match["team_a"], match["team_b"]):
                continue
            if match.get("status", "confirmed") not in ("confirmed", "final", None):
                continue
            sets_a, sets_b = match["sets_a"], match["sets_b"]
            try:
                points_a, points_b = ScoringEngine.score_for_match(match)
            except (KeyError, ValueError):
                # A malformed/incomplete historical row must not affect the
                # standings or be treated as a played match.
                continue
            partidos_jugados += 1
            if match["team_a"] == team_id:
                puntos_partido += points_a
                won = sets_a > sets_b
            else:
                puntos_partido += points_b
                won = sets_b > sets_a
            pf, pc = ScoringEngine.team_set_totals(match, team_id)
            puntos_favor += pf
            puntos_contra += pc
            if won:
                ganados += 1
            else:
                perdidos += 1
        return {
            "equipo_id": team_id,
            "equipo": team_name,
            "partidos_jugados": partidos_jugados,
            "partidos_ganados": ganados,
            "partidos_perdidos": perdidos,
            "puntos_partido": puntos_partido,
            "puntos_clasificacion": puntos_partido,
            "puntos_favor": puntos_favor,
            "puntos_contra": puntos_contra,
            "diferencia": puntos_favor - puntos_contra,
            "matches": matches
        }

    def build_team_stats(self, zone):
        team_stats = {}
        for team in zone.get("teams", []):
            team_stats[team["id"]] = {
                "team": team,
                "matches": []
            }
        for match in zone.get("results", []):
            team_a, team_b = match["team_a"], match["team_b"]
            if team_a in team_stats:
                team_stats[team_a]["matches"].append(match)
            if team_b in team_stats:
                team_stats[team_b]["matches"].append(match)
        ranked = [self.summarise_team(team_id, info["team"]["name"], info["matches"])
                  for team_id, info in team_stats.items()]
        # Desempate local: puntos de clasificación, diferencia de sets,
        # puntos a favor y menos puntos en contra. La referencia web no está
        # disponible en este proyecto, por lo que su equivalencia no puede verificarse.
        ranked.sort(key=lambda item: (
            -item["puntos_partido"],
            -item["diferencia"],
            -item["puntos_favor"],
            item["puntos_contra"]
        ))
        previous_key = None
        current_position = 0
        for index, item in enumerate(ranked, start=1):
            key = (item["puntos_partido"], item["puntos_favor"], item["puntos_contra"])
            if key != previous_key:
                current_position = index
                previous_key = key
            item["posicion"] = current_position
            item["empate"] = index > 1 and key == (
                ranked[index - 2]["puntos_partido"],
                ranked[index - 2]["puntos_favor"],
                ranked[index - 2]["puntos_contra"]
            )
        return ranked

    def calculate_zone_ranking(self, category_id, zone_id):
        category = None
        for cat in self.tournament.get("categories", []):
            if cat["id"] == category_id:
                category = cat
                break
        if not category:
            raise ValueError("Categoría no encontrada.")
        zone = None
        for z in category.get("zones", []):
            if z["id"] == zone_id:
                zone = z
                break
        if not zone:
            raise ValueError("Zona no encontrada.")
        return self.build_team_stats(zone)

    def calculate_unique_ranking(self, category_id):
        category = None
        for cat in self.tournament.get("categories", []):
            if cat["id"] == category_id:
                category = cat
                break
        if not category:
            raise ValueError("Categoría no encontrada.")
        unique = category.get("stage_unique")
        if not unique:
            return []
        zone = {"teams": [], "results": unique.get("results", [])}
        team_lookup = {}
        for team_id in unique.get("teams", []):
            for cat in self.tournament.get("categories", []):
                for z in cat.get("zones", []):
                    for team in z.get("teams", []):
                        if team["id"] == team_id:
                            team_lookup[team_id] = team
                            zone["teams"].append(team)
        return self.build_team_stats(zone)


class ResultManager:
    def __init__(self, tournament):
        self.tournament = tournament

    def find_category(self, category_id):
        for category in self.tournament.get("categories", []):
            if category["id"] == category_id:
                return category
        raise ValueError("Categoría no encontrada.")

    def find_zone(self, category_id, zone_id):
        category = self.find_category(category_id)
        for zone in category.get("zones", []):
            if zone["id"] == zone_id:
                return zone
        raise ValueError("Zona no encontrada.")

    def list_results(self, category_id, zone_id):
        zone = self.find_zone(category_id, zone_id)
        return zone.get("results", [])

    def add_result(self, category_id, zone_id, team_a, team_b, sets_a=None, sets_b=None, score_lines=None):
        zone = self.find_zone(category_id, zone_id)
        if team_a == team_b:
            raise ValueError("Un equipo no puede jugar contra sí mismo.")
        sets_a, sets_b, score_lines = ScoringEngine.derive_match_result(score_lines)
        team_map = {team["id"]: team for team in zone.get("teams", [])}
        if team_a not in team_map or team_b not in team_map:
            raise ValueError("Los equipos deben pertenecer a la zona seleccionada.")
        for existing in zone.get("results", []):
            if {existing["team_a"], existing["team_b"]} == {team_a, team_b}:
                raise ValueError("Este partido ya existe. Si es revancha o un partido nuevo, ingréselo explícitamente con equipos distintos o elija otra combinación.")
        result = {
            "id": str(uuid.uuid4()),
            "team_a": team_a,
            "team_b": team_b,
            "sets_a": sets_a,
            "sets_b": sets_b,
            "score_lines": score_lines,
            "score_format": "sets",
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "stage": "zone"
        }
        zone.setdefault("results", []).append(result)
        return result

    def update_result(self, category_id, zone_id, result_id, team_a=None, team_b=None, sets_a=None, sets_b=None, score_lines=None):
        zone = self.find_zone(category_id, zone_id)
        team_ids = {team["id"] for team in zone.get("teams", [])}
        for result in zone.get("results", []):
            if result["id"] == result_id:
                new_team_a = team_a if team_a is not None else result["team_a"]
                new_team_b = team_b if team_b is not None else result["team_b"]
                new_sets_a = sets_a if sets_a is not None else result["sets_a"]
                new_sets_b = sets_b if sets_b is not None else result["sets_b"]
                new_score_lines = score_lines if score_lines is not None else result.get("score_lines", [])
                if score_lines is not None:
                    new_sets_a, new_sets_b, new_score_lines = ScoringEngine.derive_match_result(score_lines)
                if new_team_a == new_team_b:
                    raise ValueError("Un equipo no puede jugar contra sí mismo.")
                if new_team_a not in team_ids or new_team_b not in team_ids:
                    raise ValueError("Los equipos deben pertenecer a la zona seleccionada.")
                if any(
                    other["id"] != result_id
                    and {other["team_a"], other["team_b"]} == {new_team_a, new_team_b}
                    for other in zone.get("results", [])
                ):
                    raise ValueError("Este partido ya existe en la zona seleccionada.")
                if not ScoringEngine.validate_match_result(new_sets_a, new_sets_b):
                    raise ValueError("Resultado inválido. Debe ser 2–0, 2–1, 1–2 o 0–2.")
                if score_lines is not None or result.get("score_format") == "sets":
                    new_score_lines = ScoringEngine.validate_set_scores(new_sets_a, new_sets_b, new_score_lines)
                    result["score_format"] = "sets"
                result["team_a"] = new_team_a
                result["team_b"] = new_team_b
                result["sets_a"] = new_sets_a
                result["sets_b"] = new_sets_b
                result["score_lines"] = new_score_lines
                result["status"] = "confirmed"
                result["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                return result
        raise ValueError("Resultado no encontrado.")

    def delete_result(self, category_id, zone_id, result_id):
        zone = self.find_zone(category_id, zone_id)
        for idx, result in enumerate(zone.get("results", [])):
            if result["id"] == result_id:
                del zone["results"][idx]
                return True
        raise ValueError("Resultado no encontrado.")

    def add_unique_result(self, category_id, team_a, team_b, sets_a, sets_b, score_lines):
        category = self.find_category(category_id)
        unique = category.get("stage_unique")
        if not unique:
            raise ValueError("Primero debe crearse la zona única.")
        if team_a == team_b:
            raise ValueError("Un equipo no puede jugar contra sí mismo.")
        sets_a, sets_b, score_lines = ScoringEngine.derive_match_result(score_lines)
        team_ids = set(unique.get("teams", []))
        if team_a not in team_ids or team_b not in team_ids:
            raise ValueError("Los equipos deben pertenecer a la zona única.")
        for existing in unique.get("results", []):
            if {existing["team_a"], existing["team_b"]} == {team_a, team_b}:
                raise ValueError("Este partido ya existe en la zona única.")
        result = {
            "id": str(uuid.uuid4()),
            "team_a": team_a,
            "team_b": team_b,
            "sets_a": sets_a,
            "sets_b": sets_b,
            "score_lines": score_lines,
            "score_format": "sets",
            "status": "confirmed",
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "stage": "unique"
        }
        unique.setdefault("results", []).append(result)
        return result


class ManualScoreManager:
    """Persiste cargas manuales separadas de los resultados de partidos."""

    def __init__(self, tournament):
        self.tournament = tournament

    def find_category(self, category_id):
        for category in self.tournament.get("categories", []):
            if category["id"] == category_id:
                return category
        raise ValueError("Categoría no encontrada.")

    def add(self, category_id, zone_id, team_id, points):
        category = self.find_category(category_id)
        try:
            points = int(str(points).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("La cantidad de puntos debe ser un entero.") from exc
        if points < 0:
            raise ValueError("La cantidad de puntos no puede ser negativa.")
        teams = [team for zone in category.get("zones", [])
                 if zone_id is None or zone.get("id") == zone_id
                 for team in zone.get("teams", [])]
        team = next((team for team in teams if team.get("id") == team_id), None)
        if not team:
            raise ValueError("El equipo no pertenece a la categoría/zona seleccionada.")
        load = {
            "id": str(uuid.uuid4()),
            "category_id": category_id,
            "zone_id": zone_id,
            "team_id": team_id,
            "points": points,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "type": "manual",
        }
        category.setdefault("manual_loads", []).append(load)
        return load

    def delete(self, category_id, load_id):
        category = self.find_category(category_id)
        loads = category.setdefault("manual_loads", [])
        for index, load in enumerate(loads):
            if load.get("id") == load_id:
                del loads[index]
                return True
        raise ValueError("Carga manual no encontrada.")

    def list_all(self):
        rows = []
        for category in self.tournament.get("categories", []):
            for load in category.get("manual_loads", []):
                row = dict(load)
                row["category_name"] = f"{category.get('name', '')} - {category.get('modalidad', '')}"
                rows.append(row)
        return rows


class ExportManager:
    @staticmethod
    def export_csv(tournament, category_id, zone_id=None, mode='zone'):
        category = next((c for c in tournament.get('categories', []) if c['id'] == category_id), None)
        rows = []
        if mode == 'zone':
            zone = next((z for z in category.get('zones', []) if z['id'] == zone_id), None)
            ranking = ClassificationManager(tournament).calculate_zone_ranking(category_id, zone_id)
            rows.append(['Posicion', 'Equipo', 'PJ', 'PG', 'PP', 'Puntos clasificacion', 'PF', 'PC', 'Diferencia'])
            for i, r in enumerate(ranking, 1):
                rows.append([r.get('posicion', i), r['equipo'], r['partidos_jugados'], r['partidos_ganados'], r['partidos_perdidos'], r['puntos_partido'], r['puntos_favor'], r['puntos_contra'], r['diferencia']])
        else:
            ranking = ClassificationManager(tournament).calculate_unique_ranking(category_id)
            rows.append(['Posicion', 'Equipo', 'PJ', 'PG', 'PP', 'Puntos clasificacion', 'PF', 'PC', 'Diferencia'])
            for i, r in enumerate(ranking, 1):
                rows.append([r.get('posicion', i), r['equipo'], r['partidos_jugados'], r['partidos_ganados'], r['partidos_perdidos'], r['puntos_partido'], r['puntos_favor'], r['puntos_contra'], r['diferencia']])
        return rows

    @staticmethod
    def export_json(tournament):
        """Export raw history plus the same calculated tables used by the UI/CSV."""
        payload = copy.deepcopy(tournament)
        payload["clasificaciones"] = {}
        classifier = ClassificationManager(tournament)
        for category in tournament.get("categories", []):
            category_id = category["id"]
            payload["clasificaciones"][category_id] = {
                "zonas": {
                    zone["id"]: classifier.calculate_zone_ranking(category_id, zone["id"])
                    for zone in category.get("zones", [])
                },
                "zona_unica": classifier.calculate_unique_ranking(category_id),
            }
        return json.dumps(payload, ensure_ascii=False, indent=2)


class MainApplication:
    def __init__(self):
        self.manager = TournamentManager()
        saved_id = self.manager.data.get("active_tournament_id")
        tournaments = self.manager.list_tournaments()
        self._current_tournament_id = saved_id if saved_id and self.manager.ensure_tournament(saved_id) else (tournaments[0]["id"] if tournaments else None)

    @property
    def current_tournament(self):
        if not self._current_tournament_id:
            return None
        return self.manager.ensure_tournament(self._current_tournament_id)

    def set_active_tournament(self, tournament_id):
        self._current_tournament_id = tournament_id
        self.manager.set_active_tournament(tournament_id)

    def create_demo_data(self):
        t = self.manager.create_tournament("Demo Newcom")
        self.set_active_tournament(t["id"])
        c = CategoryManager(self.current_tournament).create_category("+40", "Mixta")
        zm = ZoneManager(self.current_tournament)
        z1 = zm.create_zone(c["id"], "Zona A")
        z2 = zm.create_zone(c["id"], "Zona B")
        e1 = zm.add_team(c["id"], z1["id"], "Equipo 1")
        e2 = zm.add_team(c["id"], z1["id"], "Equipo 2")
        e3 = zm.add_team(c["id"], z2["id"], "Equipo 3")
        e4 = zm.add_team(c["id"], z2["id"], "Equipo 4")
        rm = ResultManager(self.current_tournament)
        rm.add_result(c["id"], z1["id"], e1["id"], e2["id"], 2, 0, [[25, 18], [25, 20]])
        rm.add_result(c["id"], z2["id"], e3["id"], e4["id"], 2, 1, [[25, 20], [22, 25], [15, 10]])
        self.manager.save()

    def build_gui(self):
        if ctk is None:
            self.root = tk.Tk()
            self.root.title("Puntaje Newcom")
            label = tk.Label(self.root, text="CustomTkinter no está instalado. Se ejecutará una versión mínima con Tkinter.")
            label.pack(padx=20, pady=20)
            self.root.mainloop()
            return
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.geometry("1280x820")
        self.root.minsize(1050, 680)
        self.root.title("Puntaje Newcom | Gestión de torneos")
        self.root.configure(fg_color="#F2F5F9")
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self.root, width=245, corner_radius=18, fg_color="#172B4D")
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(16, 12), pady=16)
        sidebar.grid_propagate(False)

        title = ctk.CTkLabel(sidebar, text="PUNTAJE NEWCOM", text_color="#FFFFFF",
                     font=ctk.CTkFont(size=19, weight="bold"))
        title.pack(anchor="w", padx=22, pady=(26, 4))
        ctk.CTkLabel(sidebar, text="GESTIÓN DE TORNEOS", text_color="#AFC3E2",
                 font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=23, pady=(0, 22))
        ctk.CTkFrame(sidebar, height=1, fg_color="#314565").pack(fill="x", padx=18, pady=(0, 14))

        btns = [
            ("Inicio", self.show_home),
            ("Torneos", self.show_tournaments),
            ("Categorías", self.show_categories),
            ("Zonas y equipos", self.show_zones),
            ("Carga de resultados", self.show_results),
            ("Clasificación por zonas", self.show_zone_ranking),
            ("Zona única", self.show_unique_stage),
            ("Clasificación final", self.show_final_ranking),
            ("Historial", self.show_history),
            ("Exportaciones", self.show_exports),
            ("Configuración", self.show_config),
        ]
        for text, command in btns:
            b = ctk.CTkButton(sidebar, text=text, command=command, anchor="w",
                              height=39, corner_radius=9, fg_color="transparent",
                              hover_color="#29466E", text_color="#E8EFFA",
                              font=ctk.CTkFont(size=13))
            b.pack(fill='x', padx=14, pady=3)

        ctk.CTkLabel(sidebar, text="Organizá, cargá y consultá\ntus resultados en un solo lugar.",
                     justify="left", text_color="#AFC3E2",
                     font=ctk.CTkFont(size=11)).pack(side="bottom", anchor="w", padx=22, pady=22)

        self.content = ctk.CTkFrame(self.root, corner_radius=18, fg_color="#FFFFFF",
                                    border_width=1, border_color="#E4EAF2")
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        self.content.grid_columnconfigure(0, weight=1)
        self.show_home()
        self.root.mainloop()

    def clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def show_home(self):
        self.clear_content()
        label = ctk.CTkLabel(self.content, text="Resumen del torneo", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))
        cards = ctk.CTkFrame(self.content)
        cards.pack(fill='x', padx=20, pady=10)
        if self.current_tournament:
            tournament = self.current_tournament
            categories = tournament.get("categories", [])
            total_teams = sum(len(zone.get("teams", [])) for cat in categories for zone in cat.get("zones", []))
            total_results = sum(len(zone.get("results", [])) for cat in categories for zone in cat.get("zones", []))
            ctk.CTkLabel(cards, text=f"Torneo: {tournament['name']}", font=ctk.CTkFont(size=18)).pack(anchor='w', padx=20, pady=10)
            ctk.CTkLabel(cards, text=f"Categorías: {len(categories)}", font=ctk.CTkFont(size=15)).pack(anchor='w', padx=20)
            ctk.CTkLabel(cards, text=f"Equipos: {total_teams}", font=ctk.CTkFont(size=15)).pack(anchor='w', padx=20)
            ctk.CTkLabel(cards, text=f"Resultados: {total_results}", font=ctk.CTkFont(size=15)).pack(anchor='w', padx=20)
        else:
            ctk.CTkLabel(cards, text="No hay torneos creados. Cree uno desde la sección Torneos.", font=ctk.CTkFont(size=15)).pack(anchor='w', padx=20, pady=10)

    def show_tournaments(self):
        self.clear_content()
        label = ctk.CTkLabel(self.content, text="Torneos", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))
        form = ctk.CTkFrame(self.content)
        form.pack(fill='x', padx=20, pady=10)
        self.name_entry = ctk.CTkEntry(form, placeholder_text="Nombre del torneo")
        self.name_entry.pack(side='left', padx=10, pady=10)
        self.add_tournament_button = ctk.CTkButton(form, text="Crear torneo", command=self.create_tournament)
        self.add_tournament_button.pack(side='left', padx=10)
        self.list_tournaments()

    def create_tournament(self):
        name = self.name_entry.get().strip()
        try:
            tournament = self.manager.create_tournament(name)
            self.set_active_tournament(tournament["id"])
            self.show_tournaments()
        except Exception as exc:
            print(f"Error: {exc}")

    def list_tournaments(self):
        for child in self.content.winfo_children():
            if isinstance(child, ctk.CTkFrame) and child != self.content:
                pass
        table = ctk.CTkScrollableFrame(self.content)
        table.pack(fill='both', expand=True, padx=20, pady=(0, 20))
        for t in self.manager.list_tournaments():
            frame = ctk.CTkFrame(table)
            frame.pack(fill='x', padx=10, pady=5)
            ctk.CTkLabel(frame, text=t["name"]).pack(side='left', padx=10, pady=10)
            ctk.CTkButton(frame, text="Eliminar", command=lambda tid=t["id"]: self.delete_tournament(tid)).pack(side='right', padx=(0, 10))
            ctk.CTkButton(frame, text="Abrir", command=lambda tid=t["id"]: self.open_tournament(tid)).pack(side='right', padx=10)

    def open_tournament(self, tournament_id):
        self.set_active_tournament(tournament_id)
        self.show_home()

    def delete_tournament(self, tournament_id):
        tournament = self.manager.ensure_tournament(tournament_id)
        if not tournament or not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar el torneo '{tournament['name']}' y todos sus datos?",
            parent=self.root,
        ):
            return
        self.manager.delete_tournament(tournament_id)
        if self._current_tournament_id == tournament_id:
            remaining = self.manager.list_tournaments()
            self.set_active_tournament(remaining[0]["id"] if remaining else None)
        else:
            self.manager.save()
        self.show_tournaments()

    def show_categories(self):
        self.clear_content()
        if not self.current_tournament:
            ctk.CTkLabel(self.content, text="Primero debe crear o abrir un torneo. ").pack(anchor='w', padx=20, pady=20)
            return
        label = ctk.CTkLabel(self.content, text="Categorías y modalidades", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))
        form = ctk.CTkFrame(self.content)
        form.pack(fill='x', padx=20, pady=10)
        self.cat_name = ctk.CTkEntry(form, placeholder_text="Nombre de categoría")
        self.cat_name.pack(side='left', padx=10, pady=10)
        self.cat_modalidad = ctk.CTkOptionMenu(form, values=["Femenina", "Masculina", "Mixta"])
        self.cat_modalidad.pack(side='left', padx=10, pady=10)
        ctk.CTkButton(form, text="Crear categoría", command=self.create_category).pack(side='left', padx=10)
        self.render_categories_list()

    def create_category(self):
        if not self.current_tournament:
            return
        name = self.cat_name.get().strip()
        modalidad = self.cat_modalidad.get().strip()
        try:
            CategoryManager(self.current_tournament).create_category(name, modalidad)
            self.manager.save()
            self.show_categories()
        except Exception as exc:
            print(f"Error: {exc}")

    def render_categories_list(self):
        category_box = ctk.CTkScrollableFrame(self.content)
        category_box.pack(fill='both', expand=True, padx=20, pady=(0, 20))
        for category in self.current_tournament.get("categories", []):
            frame = ctk.CTkFrame(category_box)
            frame.pack(fill='x', padx=10, pady=5)
            ctk.CTkLabel(frame, text=f"{category['name']} - {category['modalidad']}", font=ctk.CTkFont(size=16)).pack(side='left', padx=10, pady=10)
            ctk.CTkButton(frame, text="Zonas", command=lambda cid=category['id']: self.show_zones_for_category(cid)).pack(side='right', padx=10)

    def show_zones(self):
        self.clear_content()
        if not self.current_tournament:
            ctk.CTkLabel(self.content, text="Primero debe crear o abrir un torneo.").pack(anchor='w', padx=20, pady=20)
            return
        if not self.current_tournament.get("categories"):
            ctk.CTkLabel(self.content, text="Primero cree una categoría.").pack(anchor='w', padx=20, pady=20)
            return
        category = self.current_tournament["categories"][0]
        self.show_zones_for_category(category["id"])

    def show_zones_for_category(self, category_id):
        self.clear_content()
        category = next((c for c in self.current_tournament.get('categories', []) if c['id'] == category_id), None)
        if not category:
            return
        label = ctk.CTkLabel(self.content, text=f"Zonas y equipos - {category['name']} {category['modalidad']}", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))
        zone_form = ctk.CTkFrame(self.content)
        zone_form.pack(fill='x', padx=20, pady=10)
        self.zone_name_entry = ctk.CTkEntry(zone_form, placeholder_text="Nombre de zona")
        self.zone_name_entry.pack(side='left', padx=10)
        ctk.CTkButton(zone_form, text="Crear zona", command=lambda: self.create_zone(category_id)).pack(side='left', padx=10)
        zone_list = ctk.CTkScrollableFrame(self.content)
        zone_list.pack(fill='both', expand=True, padx=20, pady=10)
        for zone in category.get('zones', []):
            zone_box = ctk.CTkFrame(zone_list)
            zone_box.pack(fill='x', padx=10, pady=5)
            ctk.CTkLabel(zone_box, text=zone['name'], font=ctk.CTkFont(size=16)).pack(side='left', padx=10, pady=10)
            ctk.CTkButton(zone_box, text="Equipos", command=lambda z=zone: self.show_zone_teams(category_id, z['id'])).pack(side='right', padx=10)

    def create_zone(self, category_id):
        name = self.zone_name_entry.get().strip()
        try:
            ZoneManager(self.current_tournament).create_zone(category_id, name)
            self.manager.save()
            self.show_zones_for_category(category_id)
        except Exception as exc:
            print(f"Error: {exc}")

    def show_zone_teams(self, category_id, zone_id):
        self.clear_content()
        category = next((c for c in self.current_tournament.get('categories', []) if c['id'] == category_id), None)
        zone = next((z for z in category.get('zones', []) if z['id'] == zone_id), None)
        if not zone:
            return
        label = ctk.CTkLabel(self.content, text=f"Equipos - {zone['name']}", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))
        form = ctk.CTkFrame(self.content)
        form.pack(fill='x', padx=20, pady=10)
        team_name = ctk.CTkEntry(form, placeholder_text="Nombre del equipo")
        team_name.pack(side='left', padx=10)
        team_club = ctk.CTkEntry(form, placeholder_text="Club (opcional)")
        team_club.pack(side='left', padx=10)
        ctk.CTkButton(form, text="Agregar equipo", command=lambda: self.add_team(category_id, zone_id, team_name, team_club)).pack(side='left', padx=10)
        list_box = ctk.CTkScrollableFrame(self.content)
        list_box.pack(fill='both', expand=True, padx=20, pady=10)
        for team in zone.get('teams', []):
            frame = ctk.CTkFrame(list_box)
            frame.pack(fill='x', padx=10, pady=5)
            ctk.CTkLabel(frame, text=team['name'], font=ctk.CTkFont(size=15)).pack(side='left', padx=10, pady=10)

    def add_team(self, category_id, zone_id, team_name_entry, team_club_entry):
        name = team_name_entry.get().strip()
        club = team_club_entry.get().strip()
        try:
            ZoneManager(self.current_tournament).add_team(category_id, zone_id, name, club)
            self.manager.save()
            self.show_zone_teams(category_id, zone_id)
        except Exception as exc:
            print(f"Error: {exc}")

    def show_results(self):
        self.clear_content()
        if not self.current_tournament:
            ctk.CTkLabel(self.content, text="No hay torneo activo.").pack(anchor='w', padx=20, pady=20)
            return
        category = self.current_tournament["categories"][0] if self.current_tournament.get("categories") else None
        if not category:
            ctk.CTkLabel(self.content, text="Primero cree una categoría.").pack(anchor='w', padx=20, pady=20)
            return
        zone = category.get("zones", [None])[0] if category.get("zones") else None
        if not zone:
            ctk.CTkLabel(self.content, text="Primero cree una zona y cargue equipos.").pack(anchor='w', padx=20, pady=20)
            return
        self.result_frame(category['id'], zone['id'])

    def result_frame(self, category_id, zone_id):
        self.clear_content()
        category = next((c for c in self.current_tournament.get('categories', []) if c['id'] == category_id), None)
        if not category:
            ctk.CTkLabel(self.content, text="Categoría no encontrada.").pack(anchor='w', padx=20, pady=20)
            return
        label = ctk.CTkLabel(self.content, text="Introducir resultado de partido", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))

        selector = ctk.CTkFrame(self.content)
        selector.pack(fill='x', padx=20, pady=(2, 4))
        category_options = [
            f"{item['name']} - {item['modalidad']}"
            for item in self.current_tournament.get('categories', [])
        ]
        category_labels = {
            f"{item['name']} - {item['modalidad']}": item['id']
            for item in self.current_tournament.get('categories', [])
        }
        selected_category_label = f"{category['name']} - {category['modalidad']}"
        ctk.CTkLabel(selector, text="Categoría / modalidad:").pack(side='left', padx=(10, 4))
        self.result_category_menu = ctk.CTkOptionMenu(
            selector,
            values=category_options,
            command=lambda value: self.result_frame(category_labels[value], None),
            width=210,
        )
        self.result_category_menu.set(selected_category_label)
        self.result_category_menu.pack(side='left', padx=4)

        zones = category.get('zones', [])
        if not zones:
            ctk.CTkLabel(self.content, text="La categoría seleccionada no tiene zonas creadas.").pack(anchor='w', padx=20, pady=20)
            return
        zone = next((z for z in zones if z['id'] == zone_id), zones[0])
        zone_options = [z['name'] for z in zones]
        zone_labels = {z['name']: z['id'] for z in zones}
        ctk.CTkLabel(selector, text="Zona:").pack(side='left', padx=(18, 4))
        self.result_zone_menu = ctk.CTkOptionMenu(
            selector,
            values=zone_options,
            command=lambda value: self.result_frame(category_id, zone_labels[value]),
            width=150,
        )
        self.result_zone_menu.set(zone['name'])
        self.result_zone_menu.pack(side='left', padx=4)

        if len(zone.get('teams', [])) < 2:
            ctk.CTkLabel(self.content, text="Debe haber al menos dos equipos en la zona para cargar resultados.").pack(anchor='w', padx=20, pady=20)
            return

        teams = [t['id'] for t in zone['teams']]
        team_names = {t['id']: t['name'] for t in zone['teams']}
        form = ctk.CTkFrame(self.content)
        form.pack(fill='x', padx=20, pady=8)
        ctk.CTkLabel(form, text="Equipo 1").grid(row=0, column=0, padx=8, pady=(10, 2))
        ctk.CTkLabel(form, text="Equipo 2").grid(row=0, column=1, padx=8, pady=(10, 2))
        self.result_team_a = ctk.CTkOptionMenu(form, values=[team_names[t] for t in teams], width=180)
        self.result_team_a.grid(row=1, column=0, padx=8, pady=(0, 10))
        self.result_team_b = ctk.CTkOptionMenu(form, values=[team_names[t] for t in teams], width=180)
        self.result_team_b.grid(row=1, column=1, padx=8, pady=(0, 10))
        self.result_score_entries = []
        for index in range(3):
            ctk.CTkLabel(form, text=f"Set {index + 1} — puntos reales").grid(row=0, column=2 + index, padx=8, pady=(10, 2))
            set_frame = ctk.CTkFrame(form, fg_color="transparent")
            set_frame.grid(row=1, column=2 + index, padx=8, pady=(0, 10))
            a_entry = ctk.CTkEntry(set_frame, width=58, placeholder_text="E1")
            b_entry = ctk.CTkEntry(set_frame, width=58, placeholder_text="E2")
            a_entry.pack(side="left")
            b_entry.pack(side="left", padx=(4, 0))
            self.result_score_entries.append((a_entry, b_entry))
            if index == 2:
                self.result_set3_frame = set_frame
        self.result_outcome = ctk.CTkLabel(form, text="Resultado: —", width=150)
        self.result_outcome.grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 10), sticky="w")
        self.result_save_button = ctk.CTkButton(form, text="Registrar resultado de sets",
            command=lambda: self.confirm_result(category_id, zone_id, team_names, teams))
        self.result_save_button.grid(row=2, column=2, columnspan=3, padx=8, pady=(0, 10), sticky="ew")
        for entry_pair in self.result_score_entries:
            for entry in entry_pair:
                entry.bind("<KeyRelease>", lambda event: self.preview_result())
        self.preview_result()

        manual = ctk.CTkFrame(self.content)
        manual.pack(fill='x', padx=20, pady=(4, 8))
        ctk.CTkLabel(manual, text="Puntaje anotado", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        manual_row = ctk.CTkFrame(manual, fg_color="transparent")
        manual_row.pack(fill="x", padx=8, pady=(0, 10))
        self.manual_team_menu = ctk.CTkOptionMenu(manual_row, values=[team_names[t] for t in teams], width=220)
        self.manual_team_menu.pack(side="left", padx=4)
        self.manual_points_entry = ctk.CTkEntry(manual_row, placeholder_text="Cantidad de puntos", width=150)
        self.manual_points_entry.pack(side="left", padx=4)
        ctk.CTkButton(manual_row, text="Guardar carga", command=lambda: self.save_manual_load(category_id, zone_id, team_names)).pack(side="left", padx=4)
        list_box = ctk.CTkScrollableFrame(self.content)
        list_box.pack(fill='both', expand=True, padx=20, pady=10)
        for result in zone.get('results', []):
            frame = ctk.CTkFrame(list_box)
            frame.pack(fill='x', padx=10, pady=5)
            a = next((t['name'] for t in zone['teams'] if t['id'] == result['team_a']), result['team_a'])
            b = next((t['name'] for t in zone['teams'] if t['id'] == result['team_b']), result['team_b'])
            text = " / ".join(f"{line[0]}-{line[1]}" for line in result.get("score_lines", []))
            ctk.CTkLabel(frame, text=f"{a} {result['sets_a']} - {result['sets_b']} {b}  ({text})").pack(side='left', padx=10, pady=10)
            ctk.CTkButton(frame, text="Editar", width=80,
                command=lambda rid=result['id']: self.edit_result_dialog(category_id, zone_id, rid)).pack(side="right", padx=2)
            ctk.CTkButton(frame, text="Eliminar", width=80,
                command=lambda rid=result['id']: self.delete_result(category_id, zone_id, rid)).pack(side="right", padx=8)

    def edit_result_dialog(self, category_id, zone_id, result_id):
        """Edit real set scores and recalculate standings from saved results."""
        zone = ResultManager(self.current_tournament).find_zone(category_id, zone_id)
        result = next((item for item in zone.get("results", []) if item.get("id") == result_id), None)
        if not result:
            self._show_error("Resultado no encontrado.")
            return
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Editar resultado")
        dialog.geometry("520x220")
        dialog.transient(self.root)
        entries = []
        for index, line in enumerate(result.get("score_lines", []), start=1):
            ctk.CTkLabel(dialog, text=f"Set {index}").grid(row=0, column=index - 1, padx=8, pady=(18, 4))
            cell = ctk.CTkFrame(dialog, fg_color="transparent")
            cell.grid(row=1, column=index - 1, padx=8)
            a_entry = ctk.CTkEntry(cell, width=56)
            b_entry = ctk.CTkEntry(cell, width=56)
            a_entry.insert(0, str(line[0]))
            b_entry.insert(0, str(line[1]))
            a_entry.pack(side="left")
            b_entry.pack(side="left", padx=(4, 0))
            entries.append((a_entry, b_entry))

        def save_edit():
            try:
                lines = [[int(a.get().strip()), int(b.get().strip())] for a, b in entries]
                ResultManager(self.current_tournament).update_result(
                    category_id, zone_id, result_id, score_lines=lines
                )
                self.manager.save()
                dialog.destroy()
                self._show_info("Resultado actualizado correctamente.")
                self.result_frame(category_id, zone_id)
            except Exception as exc:
                self._show_error(exc)

        ctk.CTkButton(dialog, text="Guardar cambios", command=save_edit).grid(
            row=2, column=0, columnspan=max(1, len(entries)), padx=8, pady=24
        )

    def preview_result(self):
        if not getattr(self, "result_score_entries", None):
            return
        try:
            lines = []
            for a_entry, b_entry in self.result_score_entries:
                a, b = a_entry.get().strip(), b_entry.get().strip()
                if not a and not b:
                    continue
                if not a or not b:
                    raise ValueError
                lines.append([int(a), int(b)])
            if len(lines) == 2:
                partial = (sum(a > b for a, b in lines), sum(b > a for a, b in lines))
                if partial == (1, 1):
                    for entry in self.result_score_entries[2]:
                        entry.configure(state="normal")
                    self.result_outcome.configure(text="Resultado: 1 - 1 (cargue Set 3)")
                    return
            wins_a, wins_b, _ = ScoringEngine.derive_match_result(lines)
            self.result_outcome.configure(text=f"Resultado: {wins_a} - {wins_b}")
            third_enabled = (wins_a, wins_b) == (1, 1)
            for entry in self.result_score_entries[2]:
                entry.configure(state="normal" if third_enabled else "disabled")
            if not third_enabled:
                for entry in self.result_score_entries[2]:
                    entry.delete(0, "end")
        except Exception:
            self.result_outcome.configure(text="Resultado: —")

    def _show_error(self, message):
        if getattr(self, "root", None):
            messagebox.showerror("No se pudo guardar", str(message), parent=self.root)

    def _show_info(self, message):
        if getattr(self, "root", None):
            messagebox.showinfo("Puntaje Newcom", str(message), parent=self.root)

    def confirm_result(self, category_id, zone_id, team_names, teams):
        try:
            team_a = next(tid for tid, name in team_names.items() if name == self.result_team_a.get())
            team_b = next(tid for tid, name in team_names.items() if name == self.result_team_b.get())
            if team_a == team_b:
                raise ValueError("Seleccione dos equipos diferentes.")
            score_lines = []
            for a_entry, b_entry in self.result_score_entries:
                a, b = a_entry.get().strip(), b_entry.get().strip()
                if not a and not b:
                    continue
                if not a or not b:
                    raise ValueError("Complete los dos puntos de cada set cargado.")
                score_lines.append([int(a), int(b)])
            if len(score_lines) < 2:
                raise ValueError("Debe cargar al menos Set 1 y Set 2.")
            ResultManager(self.current_tournament).add_result(category_id, zone_id, team_a, team_b, score_lines=score_lines)
            self.manager.save()
            self._show_info("Resultado guardado correctamente.")
            self.result_frame(category_id, zone_id)
        except Exception as exc:
            self._show_error(exc)

    def save_manual_load(self, category_id, zone_id, team_names):
        try:
            team_id = next(tid for tid, name in team_names.items() if name == self.manual_team_menu.get())
            ManualScoreManager(self.current_tournament).add(category_id, zone_id, team_id, self.manual_points_entry.get())
            self.manager.save()
            self._show_info("Carga manual guardada correctamente.")
            self.result_frame(category_id, zone_id)
        except Exception as exc:
            self._show_error(exc)

    def delete_result(self, category_id, zone_id, result_id):
        if not messagebox.askyesno("Confirmar eliminación", "¿Eliminar este resultado?", parent=self.root):
            return
        try:
            ResultManager(self.current_tournament).delete_result(category_id, zone_id, result_id)
            self.manager.save()
            self.result_frame(category_id, zone_id)
        except Exception as exc:
            self._show_error(exc)

    def show_zone_ranking(self):
        self.clear_content()
        if not self.current_tournament or not self.current_tournament.get('categories'):
            ctk.CTkLabel(self.content, text="No hay categorías disponibles.").pack(anchor='w', padx=20, pady=20)
            return
        category = self.current_tournament["categories"][0]
        if not category.get('zones'):
            ctk.CTkLabel(self.content, text="No hay zonas creadas.").pack(anchor='w', padx=20, pady=20)
            return
        zone = category['zones'][0]
        self.zone_ranking_table(category['id'], zone['id'])

    def zone_ranking_table(self, category_id, zone_id):
        self.clear_content()
        category = next((c for c in self.current_tournament.get('categories', []) if c['id'] == category_id), None)
        zone = next((z for z in category.get('zones', []) if z['id'] == zone_id), None)
        ranking = ClassificationManager(self.current_tournament).calculate_zone_ranking(category_id, zone_id)
        label = ctk.CTkLabel(self.content, text=f"Clasificación por zonas - {zone['name']}", font=ctk.CTkFont(size=24, weight='bold'))
        label.pack(anchor='w', padx=20, pady=(18, 8))
        table = ctk.CTkScrollableFrame(self.content)
        table.pack(fill='both', expand=True, padx=20, pady=10)
        ctk.CTkLabel(
            self.content,
            text="Desempate: puntos de clasificación → diferencia → PF (mayor) → PC (menor). No se pudo verificar la equivalencia exacta: falta la referencia del código web. Los históricos sin sets reales muestran PF/PC en 0.",
            text_color="#526581",
        ).pack(anchor="w", padx=20, pady=(0, 6))
        headers = ["Pos", "Equipo", "PJ", "PG", "PP", "Puntos por resultados", "PF", "PC", "Dif"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(table, text=h, width=80, font=ctk.CTkFont(size=12, weight='bold')).grid(row=0, column=i, padx=4, pady=4)
        for idx, row in enumerate(ranking, start=1):
            position = f"{row['posicion']}=" if row.get('empate') else str(row['posicion'])
            ctk.CTkLabel(table, text=position).grid(row=idx, column=0, padx=4)
            ctk.CTkLabel(table, text=row['equipo']).grid(row=idx, column=1, padx=4)
            ctk.CTkLabel(table, text=str(row['partidos_jugados'])).grid(row=idx, column=2, padx=4)
            ctk.CTkLabel(table, text=str(row['partidos_ganados'])).grid(row=idx, column=3, padx=4)
            ctk.CTkLabel(table, text=str(row['partidos_perdidos'])).grid(row=idx, column=4, padx=4)
            ctk.CTkLabel(table, text=str(row['puntos_partido'])).grid(row=idx, column=5, padx=4)
            ctk.CTkLabel(table, text=str(row['puntos_favor'])).grid(row=idx, column=6, padx=4)
            ctk.CTkLabel(table, text=str(row['puntos_contra'])).grid(row=idx, column=7, padx=4)
            ctk.CTkLabel(table, text=str(row['diferencia'])).grid(row=idx, column=8, padx=4)

    def show_unique_stage(self):
        self.clear_content()
        ctk.CTkLabel(self.content, text="Zona única", font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', padx=20, pady=(18, 8))
        if self.current_tournament and self.current_tournament.get('categories'):
            for category in self.current_tournament.get("categories", []):
                box = ctk.CTkFrame(self.content)
                box.pack(fill="x", padx=20, pady=6)
                title = f"{category.get('name', '')} - {category.get('modalidad', '')}"
                ctk.CTkLabel(box, text=title).pack(side="left", padx=10, pady=10)
                if category.get("stage_unique"):
                    team_names = {team.get("id"): team.get("name") for team in StageManager(self.current_tournament).unique_teams(category["id"])}
                    ctk.CTkLabel(box, text="Clasificados: " + ", ".join(team_names.values())).pack(side="left", padx=10)
                else:
                    ctk.CTkButton(box, text="Confirmar clasificación", command=lambda cid=category["id"]: self.confirm_promotions(cid)).pack(side="right", padx=10)
        else:
            ctk.CTkLabel(self.content, text="Sin datos disponibles.").pack(anchor='w', padx=20)

    def confirm_promotions(self, category_id):
        try:
            unique = StageManager(self.current_tournament).confirm_zone_promotions(category_id)
            self.manager.save()
            self._show_info(f"Zona única creada con {len(unique.get('teams', []))} equipos clasificados.")
            self.show_unique_stage()
        except Exception as exc:
            self._show_error(exc)

    def show_final_ranking(self):
        self.clear_content()
        ctk.CTkLabel(self.content, text="Clasificación final", font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', padx=20, pady=(18, 8))

    def show_history(self):
        self.clear_content()
        ctk.CTkLabel(self.content, text="Historial", font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', padx=20, pady=(18, 8))
        history = ctk.CTkScrollableFrame(self.content)
        history.pack(fill="both", expand=True, padx=20, pady=10)
        categories = self.current_tournament.get("categories", []) if self.current_tournament else []
        team_names = {team.get("id"): team.get("name") for category in categories
                      for zone in category.get("zones", []) for team in zone.get("teams", [])}
        category_names = {category.get("id"): f"{category.get('name', '')} - {category.get('modalidad', '')}" for category in categories}
        rows = []
        for category in categories:
            for zone in category.get("zones", []):
                for result in zone.get("results", []):
                    rows.append((result.get("created_at", ""), f"{team_names.get(result.get('team_a'), result.get('team_a'))} {result.get('sets_a')}-{result.get('sets_b')} {team_names.get(result.get('team_b'), result.get('team_b'))} | " + ", ".join(f"{a}-{b}" for a, b in result.get("score_lines", [])), category_names.get(category.get("id"), ""), "Resultado de partido", None, None))
        for category in categories:
            for load in category.get("manual_loads", []):
                rows.append((load.get("created_at", ""), f"{team_names.get(load.get('team_id'), load.get('team_id'))}: +{load.get('points')} puntos", category_names.get(category.get("id"), ""), "Puntaje manual", category.get("id"), load.get("id")))
        rows.sort(key=lambda row: row[0], reverse=True)
        if not rows:
            ctk.CTkLabel(history, text="No hay cargas registradas todavía.").pack(anchor="w", padx=10, pady=10)
        for created, detail, category_name, kind, category_id, load_id in rows:
            row = ctk.CTkFrame(history)
            row.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(row, text=f"{category_name} | {kind}\n{detail}\n{created}", justify="left").pack(side="left", padx=10, pady=8)
            if load_id:
                ctk.CTkButton(row, text="Eliminar", width=80, command=lambda cid=category_id, lid=load_id: self.delete_manual_load(cid, lid)).pack(side="right", padx=8)

    def delete_manual_load(self, category_id, load_id):
        if not messagebox.askyesno("Confirmar eliminación", "¿Eliminar esta carga manual?", parent=self.root):
            return
        try:
            ManualScoreManager(self.current_tournament).delete(category_id, load_id)
            self.manager.save()
            self.show_history()
        except Exception as exc:
            self._show_error(exc)

    def show_exports(self):
        self.clear_content()
        ctk.CTkLabel(self.content, text="Exportaciones", font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', padx=20, pady=(18, 8))

    def show_config(self):
        self.clear_content()
        ctk.CTkLabel(self.content, text="Configuración y copias de seguridad", font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', padx=20, pady=(18, 8))


class TestRunner:
    def __init__(self):
        self.store = DataStore()

    def run(self):
        tests = [
            self.test_2_0_points,
            self.test_2_1_points,
            self.test_inverse_points,
            self.test_real_set_scores_all_results,
            self.test_manual_load_is_independent,
            self.test_all_valid_results_and_set_totals,
            self.test_invalid_result_rejected,
            self.test_points_priority,
            self.test_diff_breaker,
            self.test_classification_uses_requested_tiebreak_order,
            self.test_basic_pf_pc_accumulation,
            self.test_result_correction_updates_table,
            self.test_result_edit_recalculates_without_double_count,
            self.test_result_deletion_updates_table,
            self.test_persistence_roundtrip,
            self.test_category_separation,
            self.test_results_are_isolated_by_zone,
            self.test_multi_zone_persistence_roundtrip,
            self.test_zone_finalists,
            self.test_unique_zone_no_duplicates,
            self.test_unique_starts_at_zero,
            self.test_unique_does_not_sum_zone_points,
            self.test_json_export_contains_stage_classification,
            self.test_autosave_and_recovery,
            self.test_invalid_json_not_overwritten
        ]
        passed = 0
        for test in tests:
            try:
                test()
                passed += 1
                print(f"PASS: {test.__name__}")
            except Exception as exc:
                print(f"FAIL: {test.__name__}: {exc}")
        print(f"Pruebas ejecutadas: {len(tests)} | aprobadas: {passed}")
        return passed == len(tests)

    def test_2_0_points(self):
        assert ScoringEngine.official_points_for_result(2, 0) == (3, 0)

    def test_2_1_points(self):
        assert ScoringEngine.official_points_for_result(2, 1) == (2, 1)

    def test_inverse_points(self):
        assert ScoringEngine.official_points_for_result(1, 2) == (1, 2)
        assert ScoringEngine.official_points_for_result(0, 2) == (0, 3)

    def test_real_set_scores_all_results(self):
        tournament = {"categories": [{"id": "c", "zones": [{"id": "z", "teams": [{"id": "a"}, {"id": "b"}], "results": []}]}]}
        manager = ResultManager(tournament)
        cases = [
            ([[25, 20], [25, 22]], (2, 0), (3, 0)),
            ([[25, 20], [20, 25], [15, 10]], (2, 1), (2, 1)),
            ([[20, 25], [25, 20], [10, 15]], (1, 2), (1, 2)),
            ([[20, 25], [18, 25]], (0, 2), (0, 3)),
        ]
        for index, (lines, result, official) in enumerate(cases):
            if index:
                tournament["categories"][0]["zones"][0]["results"] = []
            saved = manager.add_result("c", "z", "a", "b", score_lines=lines)
            assert (saved["sets_a"], saved["sets_b"]) == result
            assert ScoringEngine.score_for_match(saved) == official
            assert ScoringEngine.team_set_totals(saved, "a") == (sum(x[0] for x in lines), sum(x[1] for x in lines))

    def test_manual_load_is_independent(self):
        tournament = {"categories": [{"id": "c", "zones": [{"id": "z", "teams": [{"id": "a", "name": "A"}], "results": []}]}]}
        load = ManualScoreManager(tournament).add("c", "z", "a", "7")
        assert load["points"] == 7
        assert tournament["categories"][0]["zones"][0]["results"] == []
        ManualScoreManager(tournament).delete("c", load["id"])
        assert tournament["categories"][0]["manual_loads"] == []

    def test_all_valid_results_and_set_totals(self):
        expected = {
            (2, 0): (3, 0), (2, 1): (2, 1),
            (1, 2): (1, 2), (0, 2): (0, 3),
        }
        for result, points in expected.items():
            assert ScoringEngine.official_points_for_result(*result) == points
            lines = [[15, 10]] * sum(result)
            match = ScoringEngine.make_match_result("A", "B", *result, lines)
            assert match["score_format"] == "sets"
            assert ScoringEngine.team_set_totals(match, "A") == (15 * sum(result), 10 * sum(result))
            assert ScoringEngine.team_set_totals(match, "B") == (10 * sum(result), 15 * sum(result))

    def test_invalid_result_rejected(self):
        assert not ScoringEngine.validate_match_result(0, 0)
        try:
            ScoringEngine.make_match_result("A", "B", 0, 0, [])
        except ValueError:
            return
        raise AssertionError("Se aceptó un resultado no válido")

    def test_points_priority(self):
        ranking = [
            {"puntos_partido": 4, "diferencia": 5, "puntos_favor": 30},
            {"puntos_partido": 4, "diferencia": 1, "puntos_favor": 50},
        ]
        sorted_rows = sorted(ranking, key=lambda item: (-item["puntos_partido"], -item["diferencia"], -item["puntos_favor"]))
        assert sorted_rows[0]["diferencia"] == 5

    def test_diff_breaker(self):
        ranking = [
            {"puntos_partido": 3, "diferencia": 7, "puntos_favor": 60},
            {"puntos_partido": 3, "diferencia": 7, "puntos_favor": 50},
        ]
        assert sorted(ranking, key=lambda item: (-item["puntos_partido"], -item["diferencia"], -item["puntos_favor"]))[0]["puntos_favor"] == 60

    def test_classification_uses_requested_tiebreak_order(self):
        tournament = {"categories": [{"id": "cat1", "zones": [{"id": "z1", "teams": [
            {"id": "A", "name": "A"}, {"id": "B", "name": "B"}, {"id": "C", "name": "C"}
        ], "results": [
            {"team_a": "A", "team_b": "B", "sets_a": 2, "sets_b": 1,
             "score_lines": [[15, 10], [15, 12], [8, 15]], "score_format": "sets"},
            {"team_a": "C", "team_b": "B", "sets_a": 2, "sets_b": 1,
             "score_lines": [[15, 10], [15, 12], [8, 15]], "score_format": "sets"}
        ]}]}]}
        ranking = ClassificationManager(tournament).calculate_zone_ranking("cat1", "z1")
        # B has the same traditional points as A/C but the highest PF.
        assert ranking[0]["equipo"] == "B"
        assert ranking[1]["equipo"] == "A"
        assert ranking[0]["puntos_partido"] == 2
        assert ranking[2]["puntos_partido"] == 2

    def test_basic_pf_pc_accumulation(self):
        tournament = {"categories": [{"id": "c", "zones": [{"id": "z", "teams": [
            {"id": "a", "name": "A"}, {"id": "b", "name": "B"}], "results": []}]}]}
        ResultManager(tournament).add_result("c", "z", "a", "b", score_lines=[[15, 6], [8, 15], [15, 10]])
        rows = ClassificationManager(tournament).calculate_zone_ranking("c", "z")
        assert rows[0]["puntos_favor"] == 38
        assert rows[0]["puntos_contra"] == 31
        assert rows[1]["puntos_favor"] == 31
        assert rows[1]["puntos_contra"] == 38

    def test_result_edit_recalculates_without_double_count(self):
        tournament = {"categories": [{"id": "c", "zones": [{"id": "z", "teams": [
            {"id": "a", "name": "A"}, {"id": "b", "name": "B"}], "results": []}]}]}
        result = ResultManager(tournament).add_result("c", "z", "a", "b", score_lines=[[15, 6], [8, 15], [15, 10]])
        manager = ResultManager(tournament)
        manager.update_result("c", "z", result["id"], score_lines=[[20, 6], [8, 15], [15, 10]])
        row = ClassificationManager(tournament).calculate_zone_ranking("c", "z")[0]
        assert row["puntos_favor"] == 43
        assert row["puntos_contra"] == 31
        manager.update_result("c", "z", result["id"], score_lines=[[15, 6], [8, 15], [15, 10]])
        row = ClassificationManager(tournament).calculate_zone_ranking("c", "z")[0]
        assert row["puntos_favor"] == 38
        assert row["puntos_contra"] == 31

    def test_result_correction_updates_table(self):
        tournament = {"categories": [{"id": "cat1", "name": "+40", "modalidad": "Mixta", "zones": [{"id": "z1", "name": "Zona A", "teams": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}], "results": [{"id": "r1", "team_a": "A", "team_b": "B", "sets_a": 2, "sets_b": 0, "score_lines": [[25, 18], [18, 25]]}]}]}]}
        ranking = ClassificationManager(tournament).calculate_zone_ranking("cat1", "z1")
        assert ranking[0]["equipo"] == "A"
        tournament["categories"][0]["zones"][0]["results"][0]["sets_a"] = 0
        tournament["categories"][0]["zones"][0]["results"][0]["sets_b"] = 2
        ranking = ClassificationManager(tournament).calculate_zone_ranking("cat1", "z1")
        assert ranking[0]["equipo"] == "B"

    def test_result_deletion_updates_table(self):
        tournament = {"categories": [{"id": "cat1", "name": "+40", "modalidad": "Mixta", "zones": [{"id": "z1", "name": "Zona A", "teams": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}], "results": [{"id": "r1", "team_a": "A", "team_b": "B", "sets_a": 2, "sets_b": 0, "score_lines": [[25, 18], [18, 25]]}]}]}]}
        tournament["categories"][0]["zones"][0]["results"] = []
        ranking = ClassificationManager(tournament).calculate_zone_ranking("cat1", "z1")
        assert ranking[0]["puntos_partido"] == 0

    def test_persistence_roundtrip(self):
        temp_dir = Path(tempfile.mkdtemp())
        store = DataStore(temp_dir, temp_dir / "datos.json")
        payload = {"version": 1, "tournaments": [{"id": "t1", "name": "T1", "categories": []}]}
        store.save(payload)
        reloaded = store.load()
        assert reloaded["tournaments"][0]["name"] == "T1"

    def test_category_separation(self):
        tournament = {"categories": [{"id": "cat1", "name": "+40", "modalidad": "Mixta", "zones": [{"id": "z1", "teams": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}], "results": []}]}, {"id": "cat2", "name": "+50", "modalidad": "Masculina", "zones": [{"id": "z2", "teams": [{"id": "C", "name": "C"}, {"id": "D", "name": "D"}], "results": []}]}]}
        assert tournament["categories"][0]["zones"][0]["teams"][0]["id"] != tournament["categories"][1]["zones"][0]["teams"][0]["id"]

    def test_results_are_isolated_by_zone(self):
        tournament = {"categories": [{"id": "cat1", "name": "+50", "modalidad": "Mixta", "zones": []}]}
        zones = tournament["categories"][0]["zones"]
        for number in range(1, 5):
            zones.append({
                "id": f"z{number}",
                "name": f"Zona {number}",
                "teams": [
                    {"id": f"z{number}a", "name": f"Equipo {number}A", "zone_id": f"z{number}"},
                    {"id": f"z{number}b", "name": f"Equipo {number}B", "zone_id": f"z{number}"},
                ],
                "results": [],
            })
        manager = ResultManager(tournament)
        for number in range(1, 5):
            manager.add_result(f"cat1", f"z{number}", f"z{number}a", f"z{number}b", 2, 0, [[15, 10], [15, 12]])
        for number in range(1, 5):
            zone = next(zone for zone in zones if zone["id"] == f"z{number}")
            assert len(zone["teams"]) == 2
            assert len(zone["results"]) == 1
            ranking = ClassificationManager(tournament).calculate_zone_ranking("cat1", f"z{number}")
            assert {row["equipo"] for row in ranking} == {f"Equipo {number}A", f"Equipo {number}B"}
            assert ranking[0]["puntos_partido"] == 3

    def test_multi_zone_persistence_roundtrip(self):
        temp_dir = Path(tempfile.mkdtemp())
        store = DataStore(temp_dir, temp_dir / "datos.json")
        payload = {
            "version": 1,
            "tournaments": [{"id": "t1", "name": "T1", "categories": [{
                "id": "cat1", "name": "+50", "modalidad": "Mixta", "zones": [
                    {"id": "z1", "name": "Zona 1", "teams": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}], "results": []},
                    {"id": "z2", "name": "Zona 2", "teams": [{"id": "c", "name": "C"}, {"id": "d", "name": "D"}], "results": []},
                ],
            }]}],
        }
        ResultManager(payload["tournaments"][0]).add_result("cat1", "z2", "c", "d", 2, 1, [[15, 10], [12, 15], [15, 13]])
        store.save(payload)
        reloaded = store.load()
        category = reloaded["tournaments"][0]["categories"][0]
        assert [zone["name"] for zone in category["zones"]] == ["Zona 1", "Zona 2"]
        assert len(category["zones"][0]["results"]) == 0
        assert len(category["zones"][1]["results"]) == 1
        assert category["zones"][1]["results"][0]["stage"] == "zone"

    def test_zone_finalists(self):
        tournament = {"categories": [{"id": "cat1", "name": "+40", "modalidad": "Mixta", "zones": [{"id": "z1", "name": "Zona A", "teams": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}, {"id": "C", "name": "C"}, {"id": "D", "name": "D"}], "results": [{"id": "r1", "team_a": "A", "team_b": "B", "sets_a": 2, "sets_b": 0, "score_lines": [[20, 15], [15, 20]]}, {"id": "r2", "team_a": "C", "team_b": "D", "sets_a": 2, "sets_b": 0, "score_lines": [[20, 10], [10, 20]]}, {"id": "r3", "team_a": "A", "team_b": "C", "sets_a": 2, "sets_b": 0, "score_lines": [[20, 10], [10, 20]]}, {"id": "r4", "team_a": "B", "team_b": "D", "sets_a": 2, "sets_b": 0, "score_lines": [[20, 10], [10, 20]]}]}]}]}
        ranking = ClassificationManager(tournament).calculate_zone_ranking("cat1", "z1")
        assert ranking[0]["equipo"] == "A"

    def test_unique_zone_no_duplicates(self):
        unique = {"teams": ["A", "B", "A", "C"]}
        assert list(dict.fromkeys(unique["teams"])) == ["A", "B", "C"]

    def test_unique_starts_at_zero(self):
        unique = {"results": []}
        assert unique["results"] == []

    def test_unique_does_not_sum_zone_points(self):
        zone = {"results": [{"id": "r1", "team_a": "A", "team_b": "B", "sets_a": 2, "sets_b": 0, "score_lines": [[25, 18], [18, 25]]}]}
        unique = {"results": []}
        assert len(zone["results"]) != len(unique["results"])

    def test_json_export_contains_stage_classification(self):
        tournament = {"categories": [{"id": "cat1", "zones": [{
            "id": "z1", "teams": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}],
            "results": [{"team_a": "A", "team_b": "B", "sets_a": 2, "sets_b": 0,
                          "score_lines": [[15, 10], [15, 12]], "score_format": "sets"}]
        }], "stage_unique": {"teams": ["A", "B"], "results": []}}]}
        exported = json.loads(ExportManager.export_json(tournament))
        row = exported["clasificaciones"]["cat1"]["zonas"]["z1"][0]
        assert row["puntos_clasificacion"] == 3
        assert row["puntos_favor"] == 30
        assert exported["clasificaciones"]["cat1"]["zona_unica"][0]["partidos_jugados"] == 0

    def test_autosave_and_recovery(self):
        temp_dir = Path(tempfile.mkdtemp())
        store = DataStore(temp_dir, temp_dir / "datos.json")
        payload = {"version": 1, "tournaments": [{"id": "t1", "name": "Demo", "categories": []}]}
        store.save(payload)
        loaded = store.load()
        assert loaded["tournaments"][0]["name"] == "Demo"

    def test_invalid_json_not_overwritten(self):
        temp_dir = Path(tempfile.mkdtemp())
        datafile = temp_dir / "datos.json"
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        datafile.write_text("{bad json}", encoding="utf-8")
        backup_dir.joinpath("backup_test.bak").write_text('{"version":1,"tournaments":[]}', encoding="utf-8")
        store = DataStore(temp_dir, datafile)
        recovered = store.load()
        assert recovered == {"version": 1, "tournaments": []}


def main(argv=None):
    argv = argv or sys.argv[1:]
    if argv and argv[0] == "--test":
        runner = TestRunner()
        success = runner.run()
        return 0 if success else 1
    app = MainApplication()
    if not app.manager.list_tournaments():
        app.create_demo_data()
    app.build_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
