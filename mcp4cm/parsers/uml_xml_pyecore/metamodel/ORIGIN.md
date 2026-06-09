# Eclipse UML2 Vendored Runtime Resources

Source: https://github.com/eclipse-uml2/uml2

Local source snapshot: `/Users/philipp/Projects/papers/uml-parser/uml2-master`

The local snapshot is not a Git checkout, so an exact upstream commit hash was
not available when these files were vendored. The bundle metadata in this
snapshot reports:

- `org.eclipse.uml2.uml`: `5.6.0.qualifier`
- `org.eclipse.uml2.types`: `2.6.0.qualifier`
- `org.eclipse.uml2.uml.resources`: `5.6.0.qualifier`

License: Eclipse Public License 2.0. See `LICENSE` and `NOTICE.md` in this
directory.

Vendored paths:

- `plugins/org.eclipse.uml2.uml/model/`
- `plugins/org.eclipse.uml2.types/model/`
- `plugins/org.eclipse.uml2.uml.resources/libraries/`
- `plugins/org.eclipse.uml2.uml.resources/profiles/`
- `plugins/org.eclipse.uml2.uml.resources/metamodels/`

These resources are used at parser runtime by
`mcp4cm.parsers.uml_xml_pyecore.UMLXMLPyEcoreParser` to load UML XML/XMI files
through PyEcore's ResourceSet and URI mapping machinery.
