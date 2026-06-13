"""Ecore parser for converting Ecore models to graph-based IR."""

import os
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Any

try:
    from pyecore.ecore import (
        EAnnotation,
        EAttribute,
        EClass,
        EDataType,
        EEnum,
        EEnumLiteral,
        EModelElement,
        ENamedElement,
        EObject,
        EOperation,
        EPackage,
        EParameter,
        EProxy,
        EReference,
        EStructuralFeature,
        ETypedElement,
        ETypeParameter,
    )
    from pyecore.resources import URI, ResourceSet
except ImportError as exc:
    raise ImportError("pyecore is required for Ecore parsing. Install it with: pip install pyecore") from exc

from mcp4cm.parsers.base import BaseParser, register_parser
from mcp4cm.parsers.diagnostics import CannotParseError, ParserRunStats, WarningType
from mcp4cm.parsers.ir import IR, Edge, Node


def _generate_id(prefix: str = "") -> str:
    """Generate a unique ID for nodes/edges."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}" if prefix else uuid.uuid4().hex[:8]


def _safe_bool(value: bool | None, default: bool) -> bool:
    return default if value is None else bool(value)


def _safe_int(value: int | None, default: int) -> int:
    return default if value is None else int(value)


def _safe_obj_label(obj: Any) -> str:
    """Return a stable label without invoking pyecore __repr__ implementations."""
    if obj is None:
        return "None"
    if isinstance(obj, EProxy):
        proxy_path = object.__getattribute__(obj, "_proxy_path") or ""
        return f"EProxy({proxy_path})" if proxy_path else "EProxy"
    obj_type = type(obj).__name__
    try:
        obj_name = getattr(obj, "name", None)
    except Exception:
        return obj_type
    if obj_name:
        return f"{obj_type}({obj_name})"
    return obj_type


@dataclass(frozen=True)
class ExternalDataTypeRef:
    """Synthetic key for external datatypes that pyecore doesn't resolve to EObjects (e.g. EString)."""

    nsURI: str
    packageName: str
    name: str


@dataclass(frozen=True)
class ExternalClassRef:
    """Synthetic key for external classes that pyecore doesn't resolve to EObjects (e.g. EObject)."""

    nsURI: str
    packageName: str
    name: str
    originResource: str = ""


@register_parser
class EcoreParser(BaseParser):
    """Parser for Ecore metamodels."""

    language = "Ecore"
    _EKEYS_ATTR_PATTERN = re.compile(rb"""\s+eKeys=(?:"[^"]*"|'[^']*')""")
    _XML_COMMENT_PATTERN = re.compile(rb"<!--.*?-->", re.DOTALL)
    _EXTERNAL_ECORE_REF_PATTERN = re.compile(r"""([A-Za-z0-9_./\\-]+\.ecore)#[^\s"'<>]*""")

    def __init__(self):
        super().__init__()
        self._dataset_root: Path | None = None
        # When enabled, we try to resolve relative external "*.ecore#..." references by
        # searching within a bounded collection scope and registering ResourceSet URI mappings.
        #
        # This improves type resolution (fewer EProxy targets / unresolved warnings), but can be
        # expensive on large collections because it may trigger many external resource loads.
        #
        # Can be disabled via env var MCP4CM_ECORE_SCOPED_URI_MAPPING=0 or via the
        # set_enable_scoped_uri_mappings() setter.
        self._enable_scoped_uri_mappings = os.getenv(
            "MCP4CM_ECORE_SCOPED_URI_MAPPING",
            os.getenv("CMBENCHMARK_ECORE_SCOPED_URI_MAPPING", "1"),
        ).strip().lower() not in {"0", "false", "no", "off"}
        # Cache basename lookups within a scope root to avoid repeated recursive scans.
        self._scope_basename_cache: dict[str, dict[str, list[Path]]] = {}
        # Per-parse caches for frequently repeated type normalization.
        self._etype_cache: dict[Any, EObject | ExternalDataTypeRef | None] = {}
        self._external_eclass_cache: dict[Any, ExternalClassRef | EObject | None] = {}
        # Reuse a ResourceSet across parses so external resources and URI mappings are cached.
        # This avoids repeatedly re-loading referenced .ecore files for every model.
        self._shared_rset = ResourceSet()
        # Per-parse fallback map for EReference eType strings (sourceClass, refName) -> eType expression.
        # Used only when pyecore partially loads due unresolved externals and drops ref.eType.
        self._reference_target_fallback_map: dict[tuple[str, str], str] = {}
        self._had_unresolved_external_load = False

    def set_dataset_root(self, dataset_root: str | Path) -> None:
        self._dataset_root = Path(dataset_root).resolve()

    def set_enable_scoped_uri_mappings(self, enabled: bool) -> None:
        """
        Enable/disable scoped URI mapping for resolving external "*.ecore#..." references.

        Disabling this is a performance knob: parsing will proceed with unresolved EProxy targets
        and create synthetic external nodes where possible, but type resolution will be less exact.
        """
        self._enable_scoped_uri_mappings = bool(enabled)
        if not self._enable_scoped_uri_mappings:
            # Ensure any previously discovered mappings don't keep enabling resolution.
            with suppress(Exception):
                self._shared_rset.uri_mapper.clear()
            # Also clear any already-cached resources; in fast mode we do per-file ResourceSets.
            try:
                for res in list(self._shared_rset.resources.values()):
                    self._shared_rset.remove_resource(res)
            except Exception:
                pass
            self._scope_basename_cache.clear()

    def parse(self, filepath: str) -> tuple[IR, ParserRunStats]:
        """
        Parse an Ecore model file into IR.

        Args:
            filepath: Path to the .ecore file

        Returns:
            Tuple of (IR object, ParserRunStats)

        Raises:
            CannotParseError: If the file is not a valid Ecore model
        """
        self._start_run()
        self._etype_cache.clear()
        self._external_eclass_cache.clear()
        self._reference_target_fallback_map.clear()
        self._had_unresolved_external_load = False

        path = Path(filepath)
        if not path.exists():
            raise CannotParseError(f"File does not exist: {filepath}")

        # Fast path: when scoped URI mappings are disabled, use a fresh ResourceSet per file.
        # This avoids cross-file cache growth and keeps per-model proxy checks cheap.
        use_shared_rset = self._enable_scoped_uri_mappings
        rset = self._shared_rset if use_shared_rset else ResourceSet()
        if use_shared_rset:
            # Do not let metamodel registrations accumulate across thousands of parses.
            # (ChainMap: first map is local to this ResourceSet instance)
            with suppress(Exception):
                rset.metamodel_registry.maps[0].clear()

        resource = None
        try:
            if self._enable_scoped_uri_mappings:
                self._register_scoped_uri_mappings(rset, path, filepath)
            resource = self._load_resource_with_compat_fallback(rset, path, filepath)

            if not resource.contents:
                raise CannotParseError("Ecore file appears to be empty")

            mm_roots = self._detect_root_packages(resource.contents)

            # Register all root packages (best-effort) so cross-resource resolution can work
            for pkg in mm_roots:
                if pkg.nsURI:
                    rset.metamodel_registry[pkg.nsURI] = pkg

        except Exception as e:
            if isinstance(e, CannotParseError):
                raise
            raise CannotParseError(f"Failed to load Ecore model: {e}") from e
        finally:
            if use_shared_rset and resource is not None:
                # Keep shared referenced resources in the ResourceSet cache, but evict
                # the "main" model resource to avoid unbounded growth of rset.resources.
                with suppress(Exception):
                    rset.remove_resource(resource)

        root_packages_meta = [
            {"name": pkg.name or "", "nsURI": pkg.nsURI or "", "nsPrefix": pkg.nsPrefix or ""} for pkg in mm_roots
        ]
        ir = IR(
            id=_generate_id("model"),
            language=self.language,
            data={
                "path": str(path.absolute()),
                "rootPackages": root_packages_meta,
                "rootPackageCount": len(mm_roots),
                "hasMultipleRootPackages": len(mm_roots) > 1,
            },
        )
        self._add_model_level_annotations(resource.contents, ir.data)

        # Collect all EObjects across all root packages (stable order, de-duplicated)
        all_eobjects: list[EObject] = []
        seen: set = set()
        for root in mm_roots:
            for obj in chain((root,), root.eAllContents()):
                if obj in seen:
                    continue
                seen.add(obj)
                all_eobjects.append(obj)

        if self._had_unresolved_external_load:
            self._reference_target_fallback_map = self._build_reference_target_fallback_map(path)

        node_eobjects: list[EObject | ExternalDataTypeRef] = self._filter_node_eobjects(all_eobjects)
        node_eobjects = self._extend_with_referenced_datatypes(node_eobjects, all_eobjects)
        node_eobjects = self._extend_with_referenced_external_classes(node_eobjects, all_eobjects)
        node_eobjects = self._extend_with_fallback_reference_targets(node_eobjects, all_eobjects)
        eobject_to_id = self._build_eobject_index(node_eobjects)

        root_pkg_set = set(mm_roots)
        for eobj in node_eobjects:
            node = self._build_node(eobj, eobject_to_id, root_pkg_set=root_pkg_set)
            if node is not None:
                ir.nodes.append(node)

        ir.edges.extend(self._build_edges(all_eobjects, eobject_to_id))

        return ir, self._stats()

    def _register_scoped_uri_mappings(self, rset: ResourceSet, path: Path, filepath: str) -> None:
        """
        Best-effort resolution for relative '*.ecore#...' references:
        - discover refs in current model text
        - search only within a bounded collection root (never whole dataset)
        - register ResourceSet uri mappings, e.g. 'EMOF.ecore' -> '/.../archive/.../EMOF.ecore'
        """
        scope_root = self._find_collection_scope_root(path)
        if scope_root is None:
            return

        refs = self._extract_external_ecore_refs(path)
        if not refs:
            return

        mapped_count = 0
        model_dir = path.parent
        for ref in refs:
            if ref in rset.uri_mapper:
                continue
            if (model_dir / ref).exists():
                continue
            resolved = self._resolve_ref_within_scope(ref, model_dir, scope_root)
            if resolved is None:
                continue
            rset.uri_mapper[ref] = str(resolved)
            mapped_count += 1

        if mapped_count > 0:
            self.warn(
                WarningType.COMPATIBILITY_ADAPTATION,
                (
                    f"Applied scoped URI mapping for {mapped_count} external resource(s) "
                    f"while loading '{filepath}' (scope: '{scope_root}')."
                ),
            )

    def _find_collection_scope_root(self, path: Path) -> Path | None:
        # Preferred: explicit dataset root from scan/profile context.
        if self._dataset_root is not None:
            try:
                rel = path.resolve().relative_to(self._dataset_root)
                if len(rel.parts) >= 1:
                    # Scope to a collection under dataset root, never dataset root itself.
                    return (self._dataset_root / rel.parts[0]).resolve()
                return None
            except ValueError:
                # Path is outside configured dataset root.
                return None

        # Fallback for standalone parser usage: infer from ".../data/<dataset>/<collection>/..."
        parts = path.resolve().parts
        if "data" in parts:
            idx = parts.index("data")
            if idx + 2 < len(parts):
                return Path(*parts[: idx + 3]).resolve()
        return None

    def _extract_external_ecore_refs(self, path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        refs = set(self._EXTERNAL_ECORE_REF_PATTERN.findall(text))
        return sorted(refs)

    def _resolve_ref_within_scope(self, ref: str, model_dir: Path, scope_root: Path) -> Path | None:
        # Try direct relative path first (still bounded by scope_root)
        if "/" in ref or "\\" in ref:
            normalized = ref.replace("\\", "/")
            direct = (scope_root / normalized).resolve()
            if direct.exists() and direct.is_file():
                return direct

        basename = Path(ref).name
        scope_key = str(scope_root)
        scope_cache = self._scope_basename_cache.setdefault(scope_key, {})
        if basename not in scope_cache:
            scope_cache[basename] = [p for p in scope_root.rglob(basename) if p.is_file()]
        candidates = scope_cache[basename]
        if not candidates:
            return None

        def score(candidate: Path) -> tuple[int, int, str]:
            rel = os.path.relpath(candidate, model_dir)
            rel_parts = Path(rel).parts
            up_count = sum(1 for part in rel_parts if part == "..")
            seg_count = len(rel_parts)
            return (up_count, seg_count, str(candidate))

        return min(candidates, key=score)

    def _load_resource_with_compat_fallback(self, rset: ResourceSet, path: Path, filepath: str):
        resource = rset.create_resource(URI(str(path.absolute())))
        try:
            self._load_resource_allowing_unresolved_external(resource, filepath)
            return resource
        except Exception as err:
            if not (self._is_unsupported_ekeys_error(err) or self._is_comment_tag_error(err)):
                raise
            original_err = err

        original_bytes = path.read_bytes()
        sanitized_bytes = original_bytes
        compat_actions: list[tuple[str, int]] = []

        if self._is_comment_tag_error(original_err):
            sanitized_bytes, removed_comments = self._XML_COMMENT_PATTERN.subn(b"", sanitized_bytes)
            if removed_comments > 0:
                compat_actions.append(("XML comments", removed_comments))

        if self._is_unsupported_ekeys_error(original_err):
            sanitized_bytes, removed_ekeys = self._EKEYS_ATTR_PATTERN.subn(b"", sanitized_bytes)
            if removed_ekeys > 0:
                compat_actions.append(("EReference attribute 'eKeys'", removed_ekeys))

        if not compat_actions:
            raise original_err

        with tempfile.NamedTemporaryFile(suffix=".ecore", delete=False) as tmp:
            tmp.write(sanitized_bytes)
            fallback_path = Path(tmp.name)

        try:
            fallback_resource = rset.create_resource(URI(str(fallback_path.absolute())))
            self._load_resource_allowing_unresolved_external(fallback_resource, filepath)
        finally:
            fallback_path.unlink(missing_ok=True)

        # The original resource failed to load; remove it from the shared ResourceSet.
        with suppress(Exception):
            rset.remove_resource(resource)

        for action, count in compat_actions:
            self.warn(
                WarningType.COMPATIBILITY_ADAPTATION,
                f"Ignored unsupported {action} ({count} occurrence(s)) while loading '{filepath}'.",
            )
        return fallback_resource

    def _force_resolve_if_already_loaded(self, proxy: EProxy, proxy_path: str) -> EObject | None:
        """
        Avoid triggering expensive autoload of external resources.

        We only force-resolve when the target resource is already present in the current
        ResourceSet (can_resolve() without loading).
        """
        # In fast mode (scoped mappings disabled), never attempt force-resolve.
        if not self._enable_scoped_uri_mappings:
            return None
        if not proxy_path:
            return None
        try:
            from_resource = getattr(proxy, "eResource", None)
            rset = getattr(from_resource, "resource_set", None)
            if rset is None or from_resource is None:
                return None
            if not rset.can_resolve(proxy_path, from_resource=from_resource):
                return None
            resolved = proxy.force_resolve()
            return resolved if isinstance(resolved, EObject) else None
        except Exception:
            return None

    def _load_resource_allowing_unresolved_external(self, resource, filepath: str) -> None:
        try:
            resource.load()
        except TypeError as e:
            # pyecore raises TypeError when an externally referenced resource can't be resolved.
            # We still want to proceed with a partially loaded model and keep the reference
            # as an EProxy so we can materialize a stub node.
            msg = str(e)
            if "cannot be resolved problem with" in msg:
                self._had_unresolved_external_load = True
                self.warn(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"External resource could not be resolved while loading '{filepath}': {msg}",
                )
            else:
                raise

    def _build_reference_target_fallback_map(self, path: Path) -> dict[tuple[str, str], str]:
        fallback_map: dict[tuple[str, str], str] = {}
        xsi_type_key = "{http://www.w3.org/2001/XMLSchema-instance}type"
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return fallback_map

        for class_elem in root.iter():
            xsi_type = class_elem.attrib.get(xsi_type_key, "")
            if not xsi_type.endswith("EClass"):
                continue
            class_name = (class_elem.attrib.get("name") or "").strip()
            if not class_name:
                continue
            for feature_elem in class_elem:
                feature_type = feature_elem.attrib.get(xsi_type_key, "")
                if not feature_type.endswith("EReference"):
                    continue
                ref_name = (feature_elem.attrib.get("name") or "").strip()
                ref_etype = (feature_elem.attrib.get("eType") or "").strip()
                if ref_name and ref_etype:
                    fallback_map[(class_name, ref_name)] = ref_etype
        return fallback_map

    def _recover_reference_target_from_fallback(
        self,
        source: EClass | None,
        ref: EReference,
        class_index: dict[str, list[EClass]],
    ) -> EClass | ExternalClassRef | None:
        if source is None:
            return None
        source_name = (getattr(source, "name", None) or "").strip()
        ref_name = (getattr(ref, "name", None) or "").strip()
        if not source_name or not ref_name:
            return None
        raw_target = self._reference_target_fallback_map.get((source_name, ref_name))
        if not raw_target:
            return None
        if raw_target.startswith("#//"):
            path_expr = raw_target.split("#//", 1)[1].strip()
            if not path_expr:
                return None
            path_parts = [part for part in path_expr.split("/") if part]
            if not path_parts:
                return None
            target_name = path_parts[-1].strip()
            package_hint = path_parts[-2].strip() if len(path_parts) >= 2 else ""
            if not target_name:
                return None
            candidates = class_index.get(target_name, [])
            if not candidates:
                return None
            if len(candidates) == 1:
                return candidates[0]

            if package_hint:
                for candidate in candidates:
                    candidate_pkg = getattr(candidate, "ePackage", None)
                    candidate_pkg_name = (getattr(candidate_pkg, "name", None) or "").strip()
                    if candidate_pkg_name == package_hint:
                        return candidate

            source_pkg = getattr(source, "ePackage", None)
            for candidate in candidates:
                if getattr(candidate, "ePackage", None) == source_pkg:
                    return candidate
            return candidates[0]

        # External reference fallback, e.g.:
        # - "ecore:EClass ../../path/EntityDsl.ecore#//Attribute"
        # - "../../path/EntityDsl.ecore#//Attribute"
        parsed = self._parse_external_eclass_ref(raw_target)
        if parsed is not None:
            return parsed
        return self._parse_proxy_eclass_ref(raw_target)

    def _is_unsupported_ekeys_error(self, err: Exception) -> bool:
        msg = str(err)
        return "Feature eKeys does not exists for type EReference" in msg

    def _is_comment_tag_error(self, err: Exception) -> bool:
        msg = str(err)
        return "Invalid tag name '<cyfunction Comment" in msg

    def _detect_root_packages(self, contents: Iterable[Any]) -> list[EPackage]:
        """
        Root detection:
        - Scan resource.contents for EPackage objects.
        - 0 packages: hard parse error
        - >=1 package: parse all of them (multi-root Ecore resources are common)
        """
        packages = [obj for obj in contents if isinstance(obj, EPackage)]
        if len(packages) == 0:
            raise CannotParseError("No EPackage found in resource")
        return packages

    def _add_model_level_annotations(self, contents: Iterable[Any], model_data: dict[str, Any]) -> None:
        """
        Collect top-level EAnnotations (directly under resource.contents) into IR.data.
        """
        annotations = [obj for obj in contents if isinstance(obj, EAnnotation)]
        if not annotations:
            return
        model_ann: dict[str, dict[str, str]] = model_data.setdefault("modelAnnotations", {})
        for ann in annotations:
            source = ann.source or ""
            block = model_ann.setdefault(source, {})
            # include nested annotations as well
            stack = [ann]
            while stack:
                current = stack.pop()
                for key, value in self._iter_annotation_details(current):
                    block[str(key)] = str(value)
                if isinstance(current, EModelElement) and current.eAnnotations:
                    stack.extend(list(current.eAnnotations))

    def _filter_node_eobjects(self, eobjects: Iterable[EObject]) -> list[EObject]:
        node_types = (
            EPackage,
            EClass,
            EDataType,
            EEnum,
            EEnumLiteral,
            EAttribute,
            EReference,
            EOperation,
            EParameter,
            ETypeParameter,
        )
        return [obj for obj in eobjects if isinstance(obj, node_types)]

    def _extend_with_referenced_datatypes(
        self,
        node_eobjects: list[EObject | ExternalDataTypeRef],
        all_eobjects: Iterable[EObject],
    ) -> list[EObject | ExternalDataTypeRef]:
        """
        Ensure that all non-enum EDataTypes referenced via eType are materialized as nodes.

        This includes external Ecore primitives like EString/EBoolean/EFloat.
        """
        existing = set(node_eobjects)
        extra: list[EObject | ExternalDataTypeRef] = []

        for obj in all_eobjects:
            if isinstance(obj, (EAttribute, EOperation, EParameter)):
                raw_etype = getattr(obj, "eType", None)
                if raw_etype is None:
                    continue
                etype = self._normalize_etype(raw_etype)
                if etype is None:
                    continue
                if isinstance(etype, EEnum):
                    continue  # already handled as normal node via eAllContents
                if isinstance(etype, (EDataType, ExternalDataTypeRef)) and etype not in existing:
                    existing.add(etype)
                    extra.append(etype)

        return node_eobjects + extra

    def _extend_with_referenced_external_classes(
        self,
        node_eobjects: list[EObject | ExternalDataTypeRef | ExternalClassRef],
        all_eobjects: Iterable[EObject],
    ) -> list[EObject | ExternalDataTypeRef | ExternalClassRef]:
        """
        Ensure that external EClasses referenced via EReference.eType are materialized as nodes.

        Common case: EObject from Ecore package.
        """
        existing = set(node_eobjects)
        extra: list[EObject | ExternalDataTypeRef | ExternalClassRef] = []

        for obj in all_eobjects:
            # External EClass reference targets
            if isinstance(obj, EReference):
                raw_target = getattr(obj, "eType", None)
                ext = self._normalize_external_eclass(raw_target)
                if ext is not None and ext not in existing:
                    existing.add(ext)
                    extra.append(ext)
            # External superclasses
            if isinstance(obj, EClass):
                for st in obj.eSuperTypes:
                    ext = self._normalize_external_eclass(st)
                    if ext is not None and ext not in existing:
                        existing.add(ext)
                        extra.append(ext)

        return list(node_eobjects) + extra

    def _extend_with_fallback_reference_targets(
        self,
        node_eobjects: list[EObject | ExternalDataTypeRef | ExternalClassRef],
        all_eobjects: Iterable[EObject],
    ) -> list[EObject | ExternalDataTypeRef | ExternalClassRef]:
        """
        Add reference targets recovered from raw XML when pyecore left EReference.eType unset.
        """
        if not self._reference_target_fallback_map:
            return list(node_eobjects)

        existing = set(node_eobjects)
        extra: list[EObject | ExternalDataTypeRef | ExternalClassRef] = []

        class_index: dict[str, list[EClass]] = {}
        for obj in all_eobjects:
            if isinstance(obj, EClass):
                cname = (obj.name or "").strip()
                if cname:
                    class_index.setdefault(cname, []).append(obj)

        for obj in all_eobjects:
            if not isinstance(obj, EClass):
                continue
            for ref in obj.eReferences:
                if getattr(ref, "eType", None) is not None:
                    continue
                recovered = self._recover_reference_target_from_fallback(obj, ref, class_index)
                if recovered is not None and recovered not in existing:
                    existing.add(recovered)
                    extra.append(recovered)

        return list(node_eobjects) + extra

    def _build_eobject_index(
        self, eobjects: Iterable[EObject | ExternalDataTypeRef | ExternalClassRef]
    ) -> dict[Any, str]:
        eobject_to_id: dict[Any, str] = {}
        for index, obj in enumerate(eobjects, start=1):
            if obj in eobject_to_id:
                self.skip_with_warning(
                    WarningType.DUPLICATE_ID,
                    f"Duplicate EObject encountered: {_safe_obj_label(obj)}",
                )
                continue
            if isinstance(obj, (ExternalDataTypeRef, ExternalClassRef)):
                node_type = "EDataType"
                if isinstance(obj, ExternalClassRef):
                    node_type = "EClass"
            else:
                node_type = obj.eClass.name if hasattr(obj, "eClass") else type(obj).__name__
            eobject_to_id[obj] = f"{node_type}_{index}"
        return eobject_to_id

    def _build_node(
        self,
        obj: EObject | ExternalDataTypeRef | ExternalClassRef,
        eobject_to_id: dict[Any, str],
        root_pkg_set: set[EPackage],
    ) -> Node | None:
        node_id = eobject_to_id.get(obj)
        if not node_id:
            self.skip_with_warning(
                WarningType.UNRESOLVED_REFERENCE,
                f"Missing node id for EObject: {_safe_obj_label(obj)}",
            )
            return None

        if isinstance(obj, ExternalDataTypeRef):
            return Node(
                id=node_id,
                type="EDataType",
                name=obj.name,
                data={
                    "external": True,
                    "nsURI": obj.nsURI,
                    "packageName": obj.packageName,
                },
            )
        if isinstance(obj, ExternalClassRef):
            return Node(
                id=node_id,
                type="EClass",
                name=obj.name,
                data={
                    "external": True,
                    **({"nsURI": obj.nsURI} if obj.nsURI else {}),
                    **({"packageName": obj.packageName} if obj.packageName else {}),
                    **({"originResource": obj.originResource} if obj.originResource else {}),
                },
            )

        node_type = obj.eClass.name if hasattr(obj, "eClass") else type(obj).__name__
        name = obj.name if isinstance(obj, ENamedElement) and obj.name else ""
        data: dict[str, Any] = {}

        if isinstance(obj, EPackage):
            data["nsURI"] = obj.nsURI or ""
            data["nsPrefix"] = obj.nsPrefix or ""
        elif isinstance(obj, EClass):
            data["abstract"] = bool(obj.abstract)
            data["interface"] = bool(obj.interface)
        elif isinstance(obj, EEnum):
            pass
        elif isinstance(obj, EDataType):
            self._fill_datatype_data(obj, data, root_pkg_set=root_pkg_set)
        elif isinstance(obj, EEnumLiteral):
            pass
        elif isinstance(obj, EAttribute):
            self._fill_typed_element_data(obj, data)
            self._fill_structural_feature_data(obj, data)
            data["iD"] = bool(obj.iD)
        elif isinstance(obj, EReference):
            self._fill_typed_element_data(obj, data)
            self._fill_structural_feature_data(obj, data)
            data["containment"] = bool(obj.containment)
            data["container"] = bool(obj.container)
            if obj.eOpposite is not None:
                data["oppositeName"] = obj.eOpposite.name or ""
                data["hasOpposite"] = True
        elif isinstance(obj, EOperation):
            self._fill_typed_element_data(obj, data)
            data["throws"] = [ex.name if isinstance(ex, ENamedElement) and ex.name else "" for ex in obj.eExceptions]
        elif isinstance(obj, EParameter):
            self._fill_typed_element_data(obj, data)
        elif isinstance(obj, ETypeParameter):
            pass

        self._fill_annotation_data(obj, data, recursive=True)

        return Node(id=node_id, type=node_type, name=name, data=data)

    def _normalize_etype(self, raw_etype: Any) -> EObject | ExternalDataTypeRef | None:
        """
        Normalize ETypedElement.eType into either a real EObject (preferred) or a synthetic
        ExternalDataTypeRef when pyecore leaves builtins as strings.
        """
        if raw_etype is None:
            return None
        cache_key = raw_etype if isinstance(raw_etype, str) else id(raw_etype)
        if cache_key in self._etype_cache:
            return self._etype_cache[cache_key]

        if isinstance(raw_etype, EProxy):
            # If uri mappings are configured, pyecore may still expose an EProxy object
            # but allow explicit resolution. Avoid autoload unless already cached.
            proxy_path = getattr(raw_etype, "_proxy_path", "") or ""
            resolved = self._force_resolve_if_already_loaded(raw_etype, proxy_path)
            if resolved is not None:
                self._etype_cache[cache_key] = resolved
                return resolved
            parsed = self._parse_proxy_datatype_ref(proxy_path)
            self._etype_cache[cache_key] = parsed
            return parsed
        if isinstance(raw_etype, EObject):
            self._etype_cache[cache_key] = raw_etype
            return raw_etype
        if isinstance(raw_etype, str):
            parsed = self._parse_external_datatype_ref(raw_etype)
            self._etype_cache[cache_key] = parsed
            return parsed
        self._etype_cache[cache_key] = None
        return None

    def _report_invalid_type_reference(self, raw_etype: Any, context: str, as_skip: bool) -> None:
        if isinstance(raw_etype, EProxy):
            proxy_path = getattr(raw_etype, "_proxy_path", "") or ""
            message = f"Invalid proxy type reference for {context}: {proxy_path!r}"
        else:
            message = f"Invalid type reference for {context}: {raw_etype!r}"
        if as_skip:
            self.skip_with_warning(WarningType.INVALID_TYPE_REFERENCE, message)
        else:
            self.warn(WarningType.INVALID_TYPE_REFERENCE, message)

    def _parse_external_datatype_ref(self, etype_str: str) -> ExternalDataTypeRef | None:
        """
        Parse strings like:
          'ecore:EDataType http://www.eclipse.org/emf/2002/Ecore#//EString'
        into ExternalDataTypeRef(nsURI='http://www.eclipse.org/emf/2002/Ecore',
                                 packageName='ecore', name='EString').
        """
        parts = etype_str.strip().split()
        if not parts:
            return None

        # Common XMI form: "<prefix>:EDataType <nsURI>#//<Name>"
        prefix_part = parts[0]
        uri_part = parts[1] if len(parts) > 1 else ""
        package_name = prefix_part.split(":")[0] if ":" in prefix_part else ""

        ns_uri = uri_part.split("#", 1)[0] if "#" in uri_part else uri_part
        fragment = uri_part.split("#", 1)[1] if "#" in uri_part else ""
        name, fragment_pkg_hint = self._extract_name_and_pkg_from_fragment(fragment)
        if not name and uri_part:
            name = uri_part.rsplit("/", 1)[-1]

        if not name:
            return None
        if not ns_uri:
            ns_uri = "http://www.eclipse.org/emf/2002/Ecore"
        if not package_name:
            package_name = fragment_pkg_hint or "ecore"

        return ExternalDataTypeRef(nsURI=ns_uri, packageName=package_name, name=name)

    def _parse_proxy_datatype_ref(self, proxy_path: str) -> ExternalDataTypeRef | None:
        """
        Parse EProxy paths like:
          'http://www.eclipse.org/emf/2002/Ecore#//EString'
        """
        proxy_path = (proxy_path or "").strip()
        if not proxy_path:
            return None
        ns_uri = proxy_path.split("#", 1)[0] if "#" in proxy_path else ""
        fragment = proxy_path.split("#", 1)[1] if "#" in proxy_path else ""
        name, fragment_pkg_hint = self._extract_name_and_pkg_from_fragment(fragment)
        if not name:
            return None
        if not ns_uri:
            ns_uri = "http://www.eclipse.org/emf/2002/Ecore"
        # Best-effort package name: Ecore's is conventionally "ecore"
        package_name = "ecore" if "emf/2002/Ecore" in ns_uri else fragment_pkg_hint
        return ExternalDataTypeRef(nsURI=ns_uri, packageName=package_name or "ecore", name=name)

    def _extract_name_and_pkg_from_fragment(self, fragment: str) -> tuple[str, str]:
        """
        Extract (name, package_hint) from common Ecore URI fragments.
        Supports:
          - '//Type'
          - 'Pkg.Type'
          - '/path/Type'
        """
        fragment = (fragment or "").strip()
        if not fragment:
            return "", ""

        token = fragment
        if token.startswith("//"):
            token = token[2:]
        token = token.strip("/")
        if "/" in token:
            token = token.split("/")[-1]
        token = token.strip()
        if not token:
            return "", ""

        if "." in token:
            parts = [p for p in token.split(".") if p]
            if not parts:
                return "", ""
            if len(parts) >= 2:
                return parts[-1], parts[-2]
            return parts[-1], ""
        return token, ""

    def _normalize_external_eclass(self, raw_etype: Any) -> ExternalClassRef | EObject | None:
        """
        For EReference.eType we want an EClass target node.
        If the type is unresolved and represented as proxy or string, create an external EClass ref.
        """
        if raw_etype is None:
            return None
        cache_key = raw_etype if isinstance(raw_etype, str) else id(raw_etype)
        if cache_key in self._external_eclass_cache:
            return self._external_eclass_cache[cache_key]
        if isinstance(raw_etype, EProxy):
            proxy_path = getattr(raw_etype, "_proxy_path", "") or ""
            resolved = self._force_resolve_if_already_loaded(raw_etype, proxy_path)
            if resolved is not None:
                self._external_eclass_cache[cache_key] = resolved
                return resolved
            parsed = self._parse_proxy_eclass_ref(proxy_path)
            self._external_eclass_cache[cache_key] = parsed
            return parsed
        if isinstance(raw_etype, str):
            # Handle 'ecore:EClass http://...#//EObject'
            parsed = self._parse_external_eclass_ref(raw_etype)
            self._external_eclass_cache[cache_key] = parsed
            return parsed
        self._external_eclass_cache[cache_key] = None
        return None

    def _parse_proxy_eclass_ref(self, proxy_path: str) -> ExternalClassRef | None:
        proxy_path = (proxy_path or "").strip()
        if not proxy_path:
            return None
        ns_uri = proxy_path.split("#", 1)[0] if "#" in proxy_path else ""
        fragment = proxy_path.split("#", 1)[1] if "#" in proxy_path else ""
        name, fragment_pkg_hint = self._extract_name_and_pkg_from_fragment(fragment)
        if not name:
            return None
        # Case 1: standard Ecore URL
        if ns_uri.startswith("http://") or ns_uri.startswith("https://"):
            package_name = "ecore" if "emf/2002/Ecore" in ns_uri else ""
            return ExternalClassRef(
                nsURI=ns_uri or "http://www.eclipse.org/emf/2002/Ecore",
                packageName=package_name or "ecore",
                name=name,
            )
        # Case 2: relative resource reference like "external.ecore#//E"
        origin = ns_uri
        return ExternalClassRef(
            nsURI="",
            packageName=fragment_pkg_hint or "",
            name=name,
            originResource=origin,
        )

    def _parse_external_eclass_ref(self, etype_str: str) -> ExternalClassRef | None:
        """
        Parse strings like:
          'ecore:EClass http://www.eclipse.org/emf/2002/Ecore#//EObject'
        """
        parts = etype_str.strip().split()
        if len(parts) < 2:
            return None
        prefix_part = parts[0]
        uri_part = parts[1]
        package_name = prefix_part.split(":")[0] if ":" in prefix_part else "ecore"
        ns_uri = uri_part.split("#", 1)[0] if "#" in uri_part else uri_part
        fragment = uri_part.split("#", 1)[1] if "#" in uri_part else ""
        name, fragment_pkg_hint = self._extract_name_and_pkg_from_fragment(fragment)
        if not name:
            return None
        if not ns_uri:
            ns_uri = "http://www.eclipse.org/emf/2002/Ecore"
        return ExternalClassRef(
            nsURI=ns_uri,
            packageName=package_name or fragment_pkg_hint or "ecore",
            name=name,
        )

    def _fill_typed_element_data(self, obj: ETypedElement, data: dict[str, Any]) -> None:
        data["ordered"] = _safe_bool(getattr(obj, "ordered", None), True)
        data["unique"] = _safe_bool(getattr(obj, "unique", None), True)
        data["lowerBound"] = _safe_int(getattr(obj, "lowerBound", None), 0)
        data["upperBound"] = _safe_int(getattr(obj, "upperBound", None), 1)
        data["required"] = data["lowerBound"] >= 1

    def _fill_structural_feature_data(self, obj: EStructuralFeature, data: dict[str, Any]) -> None:
        data["changeable"] = _safe_bool(getattr(obj, "changeable", None), True)
        data["volatile"] = _safe_bool(getattr(obj, "volatile", None), False)
        data["transient"] = _safe_bool(getattr(obj, "transient", None), False)
        data["unsettable"] = _safe_bool(getattr(obj, "unsettable", None), False)
        data["derived"] = _safe_bool(getattr(obj, "derived", None), False)

    def _fill_annotation_data(self, obj: EObject, data: dict[str, Any], recursive: bool = False) -> None:
        if not isinstance(obj, EModelElement):
            return
        if not obj.eAnnotations:
            return
        annotations: dict[str, dict[str, str]] = data.setdefault("annotations", {})
        if not recursive:
            for ann in obj.eAnnotations:
                source = ann.source or ""
                source_block = annotations.setdefault(source, {})
                for key, value in self._iter_annotation_details(ann):
                    source_block[str(key)] = str(value)
            return

        stack = list(obj.eAnnotations)
        while stack:
            ann = stack.pop()
            source = ann.source or ""
            source_block = annotations.setdefault(source, {})
            for key, value in self._iter_annotation_details(ann):
                source_block[str(key)] = str(value)
            if isinstance(ann, EModelElement) and ann.eAnnotations:
                stack.extend(list(ann.eAnnotations))

    def _fill_datatype_data(self, dtype: EDataType, data: dict[str, Any], root_pkg_set: set[EPackage]) -> None:
        """
        Minimal but informative EDataType payload, with internal/external classification.
        """
        pkg = getattr(dtype, "ePackage", None)
        internal = bool(pkg) and self._is_package_within_any_root(pkg, root_pkg_set)
        data["external"] = not internal
        if not internal:
            data["nsURI"] = pkg.nsURI if pkg is not None and pkg.nsURI else "http://www.eclipse.org/emf/2002/Ecore"
            data["packageName"] = pkg.name if pkg is not None and pkg.name else "ecore"

    def _is_package_within_any_root(self, pkg: EPackage, root_pkg_set: set[EPackage]) -> bool:
        """
        Returns True iff pkg is within any of the root packages (including the roots themselves).
        """
        current: EPackage | None = pkg
        while current is not None:
            if current in root_pkg_set:
                return True
            current = getattr(current, "eSuperPackage", None)
        return False

    def _iter_annotation_details(self, ann: EAnnotation) -> Iterable[tuple[str, str]]:
        details = getattr(ann, "details", None)
        if details is None:
            return []
        if hasattr(details, "items"):
            return list(details.items())
        entries = []
        for entry in details:
            key = getattr(entry, "key", None)
            value = getattr(entry, "value", None)
            if key is not None:
                entries.append((key, value))
        return entries

    def _build_edges(self, all_eobjects: Iterable[EObject], eobject_to_id: dict[Any, str]) -> list[Edge]:
        edges: list[Edge] = []
        created_keys: set = set()
        edge_counter = 0
        class_index: dict[str, list[EClass]] = {}
        for candidate in all_eobjects:
            if isinstance(candidate, EClass):
                cname = (candidate.name or "").strip()
                if cname:
                    class_index.setdefault(cname, []).append(candidate)

        def add_edge(
            edge_type: str,
            source: EObject,
            target: Any,
            data: dict[str, Any],
            key_hint: tuple[Any, ...],
        ) -> None:
            nonlocal edge_counter
            source_id = eobject_to_id.get(source)
            target_id = eobject_to_id.get(target)
            if not source_id or not target_id:
                self.skip_with_warning(
                    WarningType.MISSING_EDGE_ENDPOINT,
                    (f"Unresolved edge {edge_type} from {_safe_obj_label(source)} to {_safe_obj_label(target)}"),
                )
                return
            edge_key = (edge_type, source_id, target_id) + key_hint
            if edge_key in created_keys:
                self.skip_with_warning(
                    WarningType.DUPLICATE_ID,
                    f"Duplicate edge {edge_type} from {source_id} to {target_id}",
                )
                return
            created_keys.add(edge_key)
            edge_id = f"edge_{edge_counter}"
            edge_counter += 1
            edges.append(
                Edge(
                    id=edge_id,
                    sourceId=source_id,
                    targetId=target_id,
                    type=edge_type,
                    data=data,
                )
            )

        for obj in all_eobjects:
            if isinstance(obj, EPackage):
                for sub in obj.eSubpackages:
                    add_edge(
                        "Contains",
                        obj,
                        sub,
                        {"feature": "eSubpackages"},
                        ("eSubpackages",),
                    )
                for classifier in obj.eClassifiers:
                    add_edge(
                        "Contains",
                        obj,
                        classifier,
                        {"feature": "eClassifiers"},
                        ("eClassifiers",),
                    )
            elif isinstance(obj, EClass):
                for attr in obj.eAttributes:
                    add_edge(
                        "Contains",
                        obj,
                        attr,
                        {"feature": "eStructuralFeatures", "kind": "EAttribute"},
                        ("eStructuralFeatures", "EAttribute"),
                    )
                for ref in obj.eReferences:
                    add_edge(
                        "Contains",
                        obj,
                        ref,
                        {"feature": "eStructuralFeatures", "kind": "EReference"},
                        ("eStructuralFeatures", "EReference", ref.name or ""),
                    )
                for type_param in getattr(obj, "eTypeParameters", []):
                    add_edge(
                        "Contains",
                        obj,
                        type_param,
                        {"feature": "eTypeParameters"},
                        ("eTypeParameters", type_param.name or ""),
                    )
                for op in obj.eOperations:
                    add_edge(
                        "Contains",
                        obj,
                        op,
                        {"feature": "eOperations"},
                        ("eOperations",),
                    )
                for super_class in obj.eSuperTypes:
                    target = self._normalize_external_eclass(super_class) or super_class
                    add_edge(
                        "Generalization",
                        obj,
                        target,
                        {"feature": "eSuperTypes"},
                        ("eSuperTypes",),
                    )
                for ref in obj.eReferences:
                    self._add_reference_edge(ref, obj, eobject_to_id, add_edge, class_index)
            elif isinstance(obj, EEnum):
                for lit in obj.eLiterals:
                    add_edge(
                        "Contains",
                        obj,
                        lit,
                        {"feature": "eLiterals"},
                        ("eLiterals",),
                    )
            elif isinstance(obj, EOperation):
                for type_param in getattr(obj, "eTypeParameters", []):
                    add_edge(
                        "Contains",
                        obj,
                        type_param,
                        {"feature": "eTypeParameters"},
                        ("eTypeParameters", type_param.name or ""),
                    )
                for param in obj.eParameters:
                    add_edge(
                        "Contains",
                        obj,
                        param,
                        {"feature": "eParameters"},
                        ("eParameters",),
                    )

            if isinstance(obj, EAttribute):
                if obj.eType is not None:
                    target = self._normalize_etype(obj.eType)
                    if target is None:
                        self._report_invalid_type_reference(
                            obj.eType,
                            context=f"{_safe_obj_label(obj)}.eType",
                            as_skip=True,
                        )
                        continue
                    add_edge(
                        "AttributeType",
                        obj,
                        target,
                        {"feature": "eType", "kind": "attributeType"},
                        ("eType", "attributeType"),
                    )
            elif isinstance(obj, EOperation):
                if obj.eType is not None:
                    target = self._normalize_etype(obj.eType)
                    if target is None:
                        self._report_invalid_type_reference(
                            obj.eType,
                            context=f"{_safe_obj_label(obj)}.eType",
                            as_skip=True,
                        )
                        continue
                    add_edge(
                        "Type",
                        obj,
                        target,
                        {"feature": "eType", "kind": "return"},
                        ("eType", "return"),
                    )
            elif isinstance(obj, EParameter) and obj.eType is not None:
                target = self._normalize_etype(obj.eType)
                if target is None:
                    self._report_invalid_type_reference(
                        obj.eType,
                        context=f"{_safe_obj_label(obj)}.eType",
                        as_skip=True,
                    )
                    continue
                add_edge(
                    "Type",
                    obj,
                    target,
                    {"feature": "eType", "kind": "parameter"},
                    ("eType", "parameter"),
                )

        return edges

    def _add_reference_edge(
        self,
        ref: EReference,
        source_owner: EClass | None,
        eobject_to_id: dict[Any, str],
        add_edge,
        class_index: dict[str, list[EClass]],
    ) -> None:
        source = source_owner or ref.eContainingClass
        target = ref.eType
        if target is None:
            target = self._recover_reference_target_from_fallback(source, ref, class_index)
        if source is None or target is None:
            generic_target = getattr(ref, "eGenericType", None)
            if source is not None and target is None and generic_target is not None:
                self.skip_with_warning(
                    WarningType.UNSUPPORTED_GENERIC_REFERENCE,
                    f"Generic reference target is unsupported for edge construction: {_safe_obj_label(ref)}",
                )
                return
            self.skip_with_warning(
                WarningType.MISSING_EDGE_ENDPOINT,
                f"Reference missing source or target: {_safe_obj_label(ref)}",
            )
            return
        normalized_target = self._normalize_external_eclass(target)
        if normalized_target is not None:
            target = normalized_target

        data: dict[str, Any] = {
            "name": ref.name or "",
            "ordered": _safe_bool(getattr(ref, "ordered", None), True),
            "unique": _safe_bool(getattr(ref, "unique", None), True),
            "lowerBound": _safe_int(getattr(ref, "lowerBound", None), 0),
            "upperBound": _safe_int(getattr(ref, "upperBound", None), 1),
            "required": _safe_int(getattr(ref, "lowerBound", None), 0) >= 1,
            "changeable": _safe_bool(getattr(ref, "changeable", None), True),
            "volatile": _safe_bool(getattr(ref, "volatile", None), False),
            "transient": _safe_bool(getattr(ref, "transient", None), False),
            "unsettable": _safe_bool(getattr(ref, "unsettable", None), False),
            "derived": _safe_bool(getattr(ref, "derived", None), False),
            "containment": bool(ref.containment),
            "container": bool(ref.container),
        }

        self._fill_annotation_data(ref, data, recursive=True)

        if ref.eOpposite is not None:
            data["oppositeName"] = ref.eOpposite.name or ""
            data["hasOpposite"] = True

        edge_type = "Containment" if ref.containment else "Reference"
        add_edge(edge_type, source, target, data, ("eReferences", ref.name or ""))
        add_edge(
            "ReferenceType",
            ref,
            target,
            {"feature": "eType", "kind": "referenceType"},
            ("eType", "referenceType"),
        )
