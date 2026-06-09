"""Metamodel-driven UML XML/XMI parser backed by PyEcore."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, Iterable

try:
    from pyecore.ecore import EProxy
    from pyecore.resources import ResourceSet, URI
except ImportError as exc:  # pragma: no cover - dependency is declared by the package
    raise ImportError(
        "pyecore is required for UML XML PyEcore parsing. Install it with: pip install pyecore"
    ) from exc

from mcp4cm.parsers.base import BaseParser, register_parser
from mcp4cm.parsers.diagnostics import CannotParseError, ParserRunStats, WarningType
from mcp4cm.parsers.ir import Edge, IR, Node


DEFAULT_UML_NS = "http://www.eclipse.org/uml2/5.0.0/UML"
XMI_NS = "http://schema.omg.org/spec/XMI/2.1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

XMI_EXTENSION_NS_URIS = (
    "http://schema.omg.org/spec/XMI/2.1",
    "http://www.omg.org/spec/XMI/20110701",
    "http://www.omg.org/spec/XMI/20131001",
)

UML_NS_ALIASES = (
    "http://www.eclipse.org/uml2/5.0.0/UML",
    "http://www.eclipse.org/uml2/4.0.0/UML",
    "http://www.eclipse.org/uml2/3.0.0/UML",
    "http://www.eclipse.org/uml2/2.1.0/UML",
    "http://www.eclipse.org/uml2/2.0.0/UML",
    "http://www.omg.org/spec/UML/20131001",
)

PRIMITIVE_TYPES_URI_MARKERS = (
    "PrimitiveTypes.xmi",
    "UMLPrimitiveTypes.library.uml",
    "GenMyModelPrimitiveTypes.library.uml",
    "XMLPrimitiveTypes.library.uml",
)


@dataclass(frozen=True)
class UMLMetamodelPaths:
    uml_ecore: Path
    types_ecore: Path
    uml_primitive_library: Path
    xml_primitive_library: Path
    uml_profiles_dir: Path
    uml_libraries_dir: Path
    uml_metamodels_dir: Path


def default_metamodel_paths() -> UMLMetamodelPaths:
    root = Path(__file__).resolve().parent / "metamodel" / "plugins"
    return UMLMetamodelPaths(
        uml_ecore=root / "org.eclipse.uml2.uml/model/UML.ecore",
        types_ecore=root / "org.eclipse.uml2.types/model/Types.ecore",
        uml_primitive_library=root
        / "org.eclipse.uml2.uml.resources/libraries/UMLPrimitiveTypes.library.uml",
        xml_primitive_library=root
        / "org.eclipse.uml2.uml.resources/libraries/XMLPrimitiveTypes.library.uml",
        uml_profiles_dir=root / "org.eclipse.uml2.uml.resources/profiles",
        uml_libraries_dir=root / "org.eclipse.uml2.uml.resources/libraries",
        uml_metamodels_dir=root / "org.eclipse.uml2.uml.resources/metamodels",
    )


def ensure_metamodel_paths(paths: UMLMetamodelPaths) -> None:
    required = (
        paths.uml_ecore,
        paths.types_ecore,
        paths.uml_primitive_library,
        paths.xml_primitive_library,
        paths.uml_profiles_dir,
        paths.uml_libraries_dir,
        paths.uml_metamodels_dir,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise CannotParseError("Missing vendored UML2 metamodel resources:\n- " + "\n- ".join(missing))


def _namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _localname(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def sanitize_xmi_file(
    source_path: Path,
    target_path: Path,
    *,
    keep_only_root_namespace: str | None = None,
    drop_plain_attributes: tuple[str, ...] = (),
    drop_genmymodel_hrefs: bool = False,
) -> int:
    """Create a PyEcore-friendly XML/XMI copy and return removed extension count."""
    ET.register_namespace("xmi", XMI_NS)
    ET.register_namespace("xsi", XSI_NS)
    ET.register_namespace("uml", DEFAULT_UML_NS)

    tree = ET.parse(source_path)
    root = tree.getroot()
    parent_map = {child: parent for parent in root.iter() for child in list(parent)}

    removed = 0
    for element in list(root.iter()):
        if _localname(element.tag) == "Extension" and _namespace(element.tag) in XMI_EXTENSION_NS_URIS:
            parent = parent_map.get(element)
            if parent is not None:
                parent.remove(element)
                removed += 1

    if keep_only_root_namespace and _localname(root.tag) == "XMI":
        for child in list(root):
            if _namespace(child.tag) != keep_only_root_namespace:
                root.remove(child)

    if drop_plain_attributes:
        for element in root.iter():
            for attr_name in drop_plain_attributes:
                element.attrib.pop(attr_name, None)

    if drop_genmymodel_hrefs:
        parent_map = {child: parent for parent in root.iter() for child in list(parent)}
        for element in list(root.iter()):
            href = element.attrib.get("href")
            if isinstance(href, str) and href.startswith("genmymodel://"):
                parent = parent_map.get(element)
                if parent is not None:
                    parent.remove(element)
                continue
            for key, value in list(element.attrib.items()):
                if isinstance(value, str) and value.startswith("genmymodel://"):
                    del element.attrib[key]

    tree.write(target_path, encoding="utf-8", xml_declaration=True)
    return removed


def primitive_type_name_from_proxy_path(proxy_path: str | None) -> str | None:
    """Extract a primitive type name from a PrimitiveTypes.xmi proxy URI fragment."""
    if not proxy_path or not any(marker in proxy_path for marker in PRIMITIVE_TYPES_URI_MARKERS):
        return None
    fragment = proxy_path.rsplit("#", 1)[-1] if "#" in proxy_path else ""
    name = fragment.lstrip("/")
    return name or None


def is_primitive_types_proxy(proxy: EProxy) -> bool:
    proxy_path = getattr(proxy, "_proxy_path", None)
    return bool(
        proxy_path
        and any(marker in str(proxy_path) for marker in PRIMITIVE_TYPES_URI_MARKERS)
    )


def value_to_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        converted = [value_to_json(item) for item in value]
        return [item for item in converted if item is not None]
    if hasattr(value, "name") and hasattr(value, "value"):
        try:
            return str(value.name)
        except Exception:
            return str(value)
    return str(value)


@register_parser
class UMLXMLPyEcoreParser(BaseParser):
    """Parser for UML XML/XMI using the vendored Eclipse UML2 metamodel."""

    language = "UML-XML-PyEcore"

    def __init__(self, metamodel_paths: UMLMetamodelPaths | None = None):
        super().__init__()
        self.paths = metamodel_paths or default_metamodel_paths()
        self._initialized = False
        self._tmpdir_ctx: tempfile.TemporaryDirectory[str] | None = None
        self._tmpdir: Path | None = None
        self._sanitized_uml_primitives: Path | None = None
        self._sanitized_xml_primitives: Path | None = None
        self._types_package: Any | None = None
        self._uml_package: Any | None = None

    def parse(self, filepath: str) -> tuple[IR, ParserRunStats]:
        self._start_run()
        path = Path(filepath)
        if not path.exists():
            raise CannotParseError(f"File does not exist: {filepath}")

        try:
            self._ensure_initialized()
            rset = self._new_resource_set()
            model_to_load = self._sanitize_model_if_needed(path)
            rset.uri_mapper[f"genmymodel://{path.stem}"] = str(model_to_load)

            try:
                model_resource = rset.get_resource(URI(str(model_to_load)))
            except Exception as exc:
                message = str(exc)
                if "Operation not permited for \"incoming\" feature" in message or (
                    "Operation not permited for \"outgoing\" feature" in message
                ):
                    forced_clean_path = self._tmpdir_path() / f"{path.stem}.forced-sanitized{path.suffix}"
                    sanitize_xmi_file(
                        path,
                        forced_clean_path,
                        drop_plain_attributes=("incoming", "outgoing"),
                        drop_genmymodel_hrefs=True,
                    )
                    self.warn(
                        WarningType.COMPATIBILITY_ADAPTATION,
                        "Removed derived incoming/outgoing attributes and GenMyModel hrefs before UML loading.",
                    )
                    model_resource = rset.get_resource(URI(str(forced_clean_path)))
                else:
                    raise

            proxies = self._collect_proxies(model_resource.contents)
            unresolved = self._count_reportable_unresolved_proxies(proxies)
            if unresolved:
                self.warn(
                    WarningType.UNRESOLVED_REFERENCE,
                    f"{unresolved} PyEcore proxy reference(s) could not be resolved.",
                )

            return self._extract_ir(path.stem, model_resource), self._stats()
        except CannotParseError:
            raise
        except ET.ParseError as exc:
            raise CannotParseError(f"Failed to parse UML XML: {exc}") from exc
        except Exception as exc:
            raise CannotParseError(f"Failed to load UML model with PyEcore: {exc}") from exc

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        ensure_metamodel_paths(self.paths)
        self._tmpdir_ctx = tempfile.TemporaryDirectory(prefix="mcp4cm_uml_pye_")
        self._tmpdir = Path(self._tmpdir_ctx.name)
        self._sanitized_uml_primitives = self._tmpdir / "UMLPrimitiveTypes.sanitized.uml"
        self._sanitized_xml_primitives = self._tmpdir / "XMLPrimitiveTypes.sanitized.uml"

        sanitize_xmi_file(
            self.paths.uml_primitive_library,
            self._sanitized_uml_primitives,
            keep_only_root_namespace=DEFAULT_UML_NS,
        )
        sanitize_xmi_file(
            self.paths.xml_primitive_library,
            self._sanitized_xml_primitives,
            keep_only_root_namespace=DEFAULT_UML_NS,
        )

        bootstrap_rset = ResourceSet()
        bootstrap_rset.uri_mapper[
            "platform:/plugin/org.eclipse.emf.ecore/model/Ecore.ecore"
        ] = "http://www.eclipse.org/emf/2002/Ecore"
        bootstrap_rset.uri_mapper[
            "platform:/plugin/org.eclipse.uml2.types/model/Types.ecore"
        ] = "http://www.eclipse.org/uml2/5.0.0/Types"

        self._types_package = bootstrap_rset.get_resource(URI(str(self.paths.types_ecore))).contents[0]
        self._patch_types_datatypes(self._types_package)
        bootstrap_rset.metamodel_registry[self._types_package.nsURI] = self._types_package
        bootstrap_rset.metamodel_registry[
            "platform:/plugin/org.eclipse.uml2.types/model/Types.ecore"
        ] = self._types_package

        self._uml_package = bootstrap_rset.get_resource(URI(str(self.paths.uml_ecore))).contents[0]
        bootstrap_rset.metamodel_registry[self._uml_package.nsURI] = self._uml_package
        bootstrap_rset.metamodel_registry[
            "platform:/plugin/org.eclipse.uml2.uml/model/UML.ecore"
        ] = self._uml_package
        self._initialized = True

    @staticmethod
    def _patch_types_datatypes(types_package: Any) -> None:
        for name in ("Integer", "Long"):
            datatype = types_package.getEClassifier(name)
            if datatype is not None:
                datatype.from_string = int
                datatype.to_string = str

        bool_type = types_package.getEClassifier("Boolean")
        if bool_type is not None:
            bool_type.from_string = lambda raw: str(raw).lower() in ("true", "1")
            bool_type.to_string = lambda value: "true" if value else "false"

        unlimited = types_package.getEClassifier("UnlimitedNatural")
        if unlimited is not None:
            unlimited.from_string = lambda raw: -1 if raw == "*" else int(raw)
            unlimited.to_string = lambda value: "*" if value == -1 else str(value)

    def _tmpdir_path(self) -> Path:
        if self._tmpdir is None:
            raise CannotParseError("UML PyEcore parser was not initialized correctly.")
        return self._tmpdir

    def _new_resource_set(self) -> ResourceSet:
        assert self._types_package is not None
        assert self._uml_package is not None
        assert self._sanitized_uml_primitives is not None
        assert self._sanitized_xml_primitives is not None

        rset = ResourceSet()
        rset.uri_mapper["platform:/plugin/org.eclipse.emf.ecore/model/Ecore.ecore"] = (
            "http://www.eclipse.org/emf/2002/Ecore"
        )
        rset.uri_mapper["platform:/plugin/org.eclipse.uml2.types/model/Types.ecore"] = (
            "http://www.eclipse.org/uml2/5.0.0/Types"
        )
        rset.uri_mapper["http://www.omg.org/spec/UML/20131001/PrimitiveTypes.xmi"] = str(
            self._sanitized_uml_primitives
        )
        rset.uri_mapper["http://www.eclipse.org/uml2/5.0.0/Types"] = str(self.paths.types_ecore)
        rset.uri_mapper["http://www.eclipse.org/uml2/5.0.0/UML"] = str(self.paths.uml_ecore)
        rset.uri_mapper["http://www.eclipse.org/uml2/4.0.0/UML"] = str(self.paths.uml_ecore)
        rset.uri_mapper["http://www.eclipse.org/uml2/3.0.0/UML"] = str(self.paths.uml_ecore)
        rset.uri_mapper[
            "pathmap://GENMYMODEL_LIBRARIES/GenMyModelPrimitiveTypes.library.uml"
        ] = str(self._sanitized_xml_primitives)
        rset.uri_mapper["pathmap://UML_LIBRARIES/"] = str(self.paths.uml_libraries_dir) + "/"
        rset.uri_mapper["pathmap://UML_PROFILES/"] = str(self.paths.uml_profiles_dir) + "/"
        rset.uri_mapper["pathmap://UML_METAMODELS/"] = str(self.paths.uml_metamodels_dir) + "/"

        rset.metamodel_registry[self._types_package.nsURI] = self._types_package
        rset.metamodel_registry[
            "platform:/plugin/org.eclipse.uml2.types/model/Types.ecore"
        ] = self._types_package
        for ns_uri in UML_NS_ALIASES:
            rset.metamodel_registry[ns_uri] = self._uml_package
        rset.metamodel_registry[
            "platform:/plugin/org.eclipse.uml2.uml/model/UML.ecore"
        ] = self._uml_package
        return rset

    def _sanitize_model_if_needed(self, model_path: Path) -> Path:
        start = model_path.read_bytes()[: 512 * 1024]
        needs_sanitize = b"<xmi:Extension" in start
        if not needs_sanitize:
            return model_path

        clean_path = self._tmpdir_path() / f"{model_path.stem}.sanitized{model_path.suffix}"
        sanitize_xmi_file(
            model_path,
            clean_path,
            drop_plain_attributes=("incoming", "outgoing"),
            drop_genmymodel_hrefs=True,
        )
        return clean_path

    def _collect_proxies(self, roots: Iterable[Any]) -> list[EProxy]:
        proxies: list[EProxy] = []
        seen: set[int] = set()

        for root in roots:
            for obj in self._iter_model_objects([root]):
                for reference in obj.eClass.eAllReferences():
                    try:
                        value = obj.eGet(reference)
                    except Exception:
                        continue
                    if value is None:
                        continue
                    if reference.many:
                        try:
                            values = list(value)
                        except Exception:
                            continue
                    else:
                        values = [value]
                    for candidate in values:
                        if isinstance(candidate, EProxy):
                            key = id(candidate)
                            if key not in seen:
                                seen.add(key)
                                proxies.append(candidate)
        return proxies

    @staticmethod
    def _count_reportable_unresolved_proxies(proxies: Iterable[EProxy]) -> int:
        unresolved = 0
        for proxy in proxies:
            if proxy.resolved:
                continue
            try:
                proxy.force_resolve()
            except Exception:
                pass
            if proxy.resolved or is_primitive_types_proxy(proxy):
                continue
            unresolved += 1
        return unresolved

    @staticmethod
    def _type_reference_for_object(obj: Any) -> Any | None:
        for reference in obj.eClass.eAllReferences():
            if reference.name == "type":
                return reference
        return None

    @classmethod
    def _primitive_type_for_object(cls, obj: Any) -> str | None:
        type_reference = cls._type_reference_for_object(obj)
        if type_reference is None:
            return None
        try:
            type_value = obj.eGet(type_reference)
        except Exception:
            return None
        if not isinstance(type_value, EProxy):
            return None
        return primitive_type_name_from_proxy_path(getattr(type_value, "_proxy_path", None))

    def _iter_model_objects(self, roots: Iterable[Any]) -> Iterable[Any]:
        containment_cache: dict[int, list[Any]] = {}
        visited: set[int] = set()
        stack: list[Any] = list(roots)

        while stack:
            obj = stack.pop()
            obj_id = id(obj)
            if obj_id in visited:
                continue
            visited.add(obj_id)
            yield obj

            class_key = id(obj.eClass)
            containment_refs = containment_cache.get(class_key)
            if containment_refs is None:
                containment_refs = [
                    ref
                    for ref in obj.eClass.eAllReferences()
                    if ref.containment and not ref.derived and not ref.transient
                ]
                containment_cache[class_key] = containment_refs

            for ref in containment_refs:
                try:
                    value = obj.eGet(ref)
                except Exception:
                    continue
                if value is None:
                    continue
                if ref.many:
                    try:
                        children = list(value)
                    except Exception:
                        continue
                else:
                    children = [value]
                for child in children:
                    if child is not None and not isinstance(child, EProxy):
                        stack.append(child)

    def _extract_ir(self, model_id: str, model_resource: Any) -> IR:
        roots = model_resource.contents
        objects = list(self._iter_model_objects(roots))

        node_ids: dict[int, str] = {}
        nodes: list[Node] = []
        anonymous_counter = 0
        attribute_cache: dict[int, list[Any]] = {}
        reference_cache: dict[int, list[Any]] = {}
        model_name = ""

        for obj in objects:
            obj_key = id(obj)
            internal_id = getattr(obj, "_internal_id", None)
            if internal_id:
                node_id = str(internal_id)
            else:
                anonymous_counter += 1
                node_id = f"{model_id}__anon_{anonymous_counter}"

            node_ids[obj_key] = node_id
            try:
                name_value = getattr(obj, "name", None)
            except Exception:
                name_value = None
            node_name = str(name_value) if name_value is not None else ""
            if not model_name and node_name:
                model_name = node_name

            data: dict[str, Any] = {}
            class_key = id(obj.eClass)
            attributes = attribute_cache.get(class_key)
            if attributes is None:
                attributes = list(obj.eClass.eAllAttributes())
                attribute_cache[class_key] = attributes

            for attr in attributes:
                if attr.name == "name":
                    continue
                try:
                    value = obj.eGet(attr)
                except Exception:
                    continue
                json_value = value_to_json(value)
                if json_value is None or (isinstance(json_value, list) and not json_value):
                    continue
                data[attr.name] = json_value

            element_type = obj.eClass.name
            primitive_type = self._primitive_type_for_object(obj)
            if primitive_type:
                nodes.append(
                    Node(
                        id=node_id,
                        type=primitive_type,
                        name=node_name,
                        eClass=element_type,
                        data=data,
                    )
                )
            else:
                nodes.append(
                    Node(id=node_id, type=element_type, name=node_name, data=data)
                )

        edges: list[Edge] = []
        edge_counter = 0
        for source_obj in objects:
            source_id = node_ids[id(source_obj)]
            class_key = id(source_obj.eClass)
            references = reference_cache.get(class_key)
            if references is None:
                references = [
                    ref
                    for ref in source_obj.eClass.eAllReferences()
                    if not ref.derived and not ref.transient
                ]
                reference_cache[class_key] = references

            for ref in references:
                try:
                    value = source_obj.eGet(ref)
                except Exception:
                    continue
                if value is None:
                    continue
                if ref.many:
                    try:
                        targets = list(value)
                    except Exception:
                        continue
                else:
                    targets = [value]

                for index, target in enumerate(targets):
                    if target is None or isinstance(target, EProxy):
                        continue
                    target_id = node_ids.get(id(target))
                    if not target_id:
                        continue

                    edge_counter += 1
                    edge_data = {
                        "containment": bool(ref.containment),
                        "many": bool(ref.many),
                    }
                    if ref.many:
                        edge_data["index"] = index
                    edges.append(
                        Edge(
                            id=f"{model_id}__e{edge_counter}",
                            sourceId=source_id,
                            targetId=target_id,
                            type=ref.name,
                            data=edge_data,
                        )
                    )

        return IR(
            id=model_id,
            language=self.language,
            data={"name": model_name, "rootCount": len(roots)},
            nodes=nodes,
            edges=edges,
        )
