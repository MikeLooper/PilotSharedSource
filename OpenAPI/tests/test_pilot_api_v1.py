"""Validation tests for the PilotApi OpenAPI specification.

Purpose:
    Checks that OpenAPI/PilotApi_v1.yaml is a valid OpenAPI 3.1 document, follows
    the conventions shared by its endpoints, and that its DTO schemas accept and
    reject sample payloads according to the Northwind database constraints.

Required inputs/arguments:
    None. Standard pytest arguments apply. Set the optional OPENAPI_SPEC
    environment variable to test a different copy of the specification.

Required environment/dependencies:
    Python 3.10+ and the packages in OpenAPI/tests/requirements.txt.

Example usage:
    python -m pip install -r OpenAPI/tests/requirements.txt
    python -m pytest OpenAPI/tests

Expected outputs and failure behavior:
    Prints a pytest summary. Exits 0 when all tests pass and non-zero on any
    failure, or if the specification cannot be loaded. Each failure names the
    specification file and line, what was found there, and how to fix it. The
    specification is never modified.
"""

import os
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import OpenAPIV31SpecValidator

SPEC_PATH = Path(
    os.environ.get("OPENAPI_SPEC", Path(__file__).parents[1] / "PilotApi_v1.yaml")
)
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
INT16_MAX = 32767
INT32_MAX = 2147483647


class UniqueKeyLoader(yaml.SafeLoader):
    """A YAML loader that rejects duplicate keys, which PyYAML otherwise overwrites."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    lambda loader, node: loader.construct_mapping(node, deep=True),
)


def map_lines(node, path=()):
    """Maps each path in a composed YAML node to its 1-based line number."""
    lines = {}
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            child = (*path, key_node.value)
            lines[child] = key_node.start_mark.line + 1
            lines.update(map_lines(value_node, child))
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            child = (*path, index)
            lines[child] = item.start_mark.line + 1
            lines.update(map_lines(item, child))
    return lines


with SPEC_PATH.open(encoding="utf-8") as spec_file:
    SPEC = yaml.load(spec_file, Loader=UniqueKeyLoader)
with SPEC_PATH.open(encoding="utf-8") as spec_file:
    SPEC_LINES = map_lines(yaml.compose(spec_file, Loader=yaml.SafeLoader))


def pointer(path):
    """Formats a path as a JSON pointer."""
    parts = (str(part).replace("~", "~0").replace("/", "~1") for part in path)
    return "#/" + "/".join(parts)


def spec_location(path):
    """Returns file:line for a path, or for its nearest existing parent."""
    line = 1
    for length in range(len(path), 0, -1):
        if path[:length] in SPEC_LINES:
            line = SPEC_LINES[path[:length]]
            break
    try:
        file_name = os.path.relpath(SPEC_PATH)
    except ValueError:
        file_name = str(SPEC_PATH)
    return f"{file_name}:{line} ({pointer(path)})"


def violation(path, problem, fix):
    """Describes where a rule was broken, what was found, and how to fix it."""
    return f"{spec_location(path)}\n  Problem: {problem}\n  Fix: {fix}"


def check(violations):
    """Fails the test with every collected violation."""
    __tracebackhide__ = True
    if violations:
        pytest.fail("\n".join(violations))


def lookup(reference):
    """Returns the object a local $ref points to, or None if it does not exist."""
    target = SPEC
    for part in reference.removeprefix("#/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target


def resolve(node):
    """Follows local $refs, returning the referenced object or {} if broken."""
    seen = set()
    while isinstance(node, dict) and "$ref" in node and node["$ref"] not in seen:
        seen.add(node["$ref"])
        node = lookup(node["$ref"]) or {}
    return node


def ref_name(node):
    """Returns the last segment of a node's $ref, or None if it has no $ref."""
    if isinstance(node, dict) and isinstance(node.get("$ref"), str):
        return node["$ref"].rsplit("/", 1)[-1]
    return None


def walk(node, path=()):
    """Yields (path, dict) for every dict nested within a node, including itself."""
    if isinstance(node, dict):
        yield path, node
        children = node.items()
    elif isinstance(node, list):
        children = enumerate(node)
    else:
        return
    for key, child in children:
        yield from walk(child, (*path, key))


COMPONENTS = SPEC.get("components", {})
OPERATIONS = [
    (path, method, operation)
    for path, item in SPEC.get("paths", {}).items()
    if isinstance(item, dict)
    for method, operation in item.items()
    # Malformed operations are reported by test_document_is_valid_openapi.
    if method in HTTP_METHODS and isinstance(operation, dict)
]
OPERATION_IDS = [f"{method} {path}" for path, method, _ in OPERATIONS]
V1_OPERATIONS = [entry for entry in OPERATIONS if entry[0].startswith("/v1/")]
V1_IDS = [f"{method} {path}" for path, method, _ in V1_OPERATIONS]
RESOURCES = sorted({path.split("/")[2] for path, _, _ in V1_OPERATIONS})


def all_schemas():
    """Returns a pytest parameter for each component schema and parameter schema."""
    entries = []
    for name, schema in COMPONENTS.get("schemas", {}).items():
        entries.append((("components", "schemas", name), schema))
    for name, parameter in COMPONENTS.get("parameters", {}).items():
        if "schema" in parameter:
            entries.append((("components", "parameters", name, "schema"), parameter["schema"]))
    for path, method, operation in OPERATIONS:
        for index, parameter in enumerate(operation.get("parameters", [])):
            if "schema" in parameter:
                entries.append((("paths", path, method, "parameters", index, "schema"), parameter["schema"]))
    return [pytest.param(path, schema, id=pointer(path)) for path, schema in entries]


def v1_operations(action):
    """Selects /v1 operations by the action segment of their path, such as 'add'."""
    return [
        pytest.param(path, method, operation, id=f"{method} {path}")
        for path, method, operation in V1_OPERATIONS
        if path.split("/")[3] == action
    ]


def operation_path(path, method, *rest):
    return ("paths", path, method, *rest)


def parameter_refs(operation):
    return {ref_name(parameter) for parameter in operation.get("parameters", [])}


def response_schema(operation, status):
    """Returns the JSON schema of a response, or None if it does not declare one."""
    response = resolve(operation.get("responses", {}).get(status, {}))
    return response.get("content", {}).get("application/json", {}).get("schema")


def schema_validator(name):
    """Builds a validator for a named component schema."""
    schema = {"$ref": f"#/components/schemas/{name}", "components": COMPONENTS}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def require_schema(name):
    """Fails the test if a named component schema does not exist."""
    __tracebackhide__ = True
    check(
        []
        if name in COMPONENTS.get("schemas", {})
        else [
            violation(
                ("components", "schemas", name),
                f"Schema {name} does not exist.",
                f"Add {name} under components/schemas, or update the samples in this test file if it was renamed.",
            )
        ]
    )


def required_header_fix(names):
    return f"Add a $ref to {', '.join(sorted(names))} under parameters."


# --- Document validity ---------------------------------------------------------


def test_document_is_valid_openapi():
    try:
        errors = list(OpenAPIV31SpecValidator(SPEC).iter_errors())
    except Exception as error:  # The validator raises, rather than reports, some errors such as broken $refs.
        check(
            [
                violation(
                    (),
                    f"The validator stopped with {type(error).__name__}: {str(error).split(' within ')[0][:300]}",
                    "Correct this element. For a broken $ref, test_all_local_references_resolve lists each location.",
                )
            ]
        )
    violations = []
    for error in errors:
        detail = error
        while detail.context:  # Report the most specific cause of a oneOf or anyOf error.
            detail = max(detail.context, key=lambda item: len(item.absolute_path))
        violations.append(
            violation(
                tuple(detail.absolute_path),
                detail.message,
                "Correct this element so it matches the OpenAPI 3.1 specification.",
            )
        )
    check(violations)


def test_document_uses_openapi_3_1():
    version = str(SPEC.get("openapi"))
    check(
        []
        if version.startswith("3.1.")
        else [violation(("openapi",), f"Found version {version}.", "Set openapi to a 3.1.x version, or update these tests for the new version.")]
    )


def test_all_local_references_resolve():
    violations = []
    for path, node in walk(SPEC):
        reference = node.get("$ref")
        if not isinstance(reference, str):
            continue
        if not reference.startswith("#/"):
            violations.append(violation((*path, "$ref"), f"{reference} is not a local reference.", "Use a reference that starts with #/."))
        elif lookup(reference) is None:
            violations.append(
                violation((*path, "$ref"), f"{reference} does not exist.", "Correct the reference, or add the missing component.")
            )
    check(violations)


@pytest.mark.parametrize("section", ["callbacks", "examples", "headers", "links", "parameters", "pathItems", "requestBodies", "responses", "schemas", "securitySchemes"])
    references = {
        node["$ref"] for _, node in walk(SPEC) if isinstance(node.get("$ref"), str)
    }
    check(
        [
            violation(("components", section, name), f"{name} is never referenced.", "Reference this component, or remove it.")
            for name in COMPONENTS.get(section, {})
            if f"#/components/{section}/{name}" not in references
        ]
    )


# --- Schema consistency --------------------------------------------------------


def schema_types(node):
    """Returns a schema node's type keyword as a list."""
    types = node.get("type")
    return types if isinstance(types, list) else [types]


@pytest.mark.parametrize("location,schema", all_schemas())
def test_schema_is_internally_consistent(location, schema):
    violations = []
    for path, node in walk(schema, location):
        if isinstance(node.get("pattern"), str):
            try:
                re.compile(node["pattern"])
            except re.error as error:
                violations.append(
                    violation((*path, "pattern"), f"Pattern {node['pattern']!r} does not compile: {error}.", "Correct the regular expression.")
                )
        for low, high in (("minimum", "maximum"), ("minLength", "maxLength")):
            if isinstance(node.get(low), (int, float)) and isinstance(node.get(high), (int, float)) and node[low] > node[high]:
                violations.append(
                    violation((*path, low), f"{low} {node[low]} is greater than {high} {node[high]}.", f"Correct {low} or {high}.")
                )
        if isinstance(node.get("required"), list) and isinstance(node.get("properties"), dict):
            for name in sorted(set(node["required"]) - set(node["properties"])):
                violations.append(
                    violation((*path, "required"), f"{name} is required but is not defined under properties.", f"Define {name}, or remove it from required.")
                )
    check(violations)


@pytest.mark.parametrize("location,schema", all_schemas())
def test_examples_and_defaults_match_their_schema(location, schema):
    violations = []
    for path, node in walk(schema, location):
        if "type" not in node:
            continue
        constraints = {key: value for key, value in node.items() if key not in ("example", "default")}
        validator = Draft202012Validator({**constraints, "components": COMPONENTS})
        for keyword in ("example", "default"):
            if keyword in node:
                violations.extend(
                    violation((*path, keyword), f"{keyword} {node[keyword]!r} is invalid: {error.message}.", f"Change the {keyword}, or correct the schema.")
                    for error in validator.iter_errors(node[keyword])
                )
    check(violations)


@pytest.mark.parametrize("location,schema", all_schemas())
def test_numeric_fields_are_not_also_strings(location, schema):
    violations = []
    for path, node in walk(schema, location):
        types = schema_types(node)
        if "integer" not in types and "number" not in types:
            continue
        if "string" in types:
            violations.append(violation((*path, "type"), f"Found types {types}.", "Remove string from the type list."))
        for keyword in sorted({"pattern", "minLength", "maxLength"} & set(node)):
            violations.append(
                violation((*path, keyword), f"{keyword} is a string keyword, but this field is numeric.", f"Remove {keyword}.")
            )
    check(violations)


@pytest.mark.parametrize("location,schema", all_schemas())
def test_integer_format_matches_its_range(location, schema):
    limits = {"int16": INT16_MAX, "int32": INT32_MAX}
    violations = []
    for path, node in walk(schema, location):
        maximum = node.get("maximum")
        declared = node.get("format")
        if not isinstance(maximum, int) or not isinstance(declared, str):
            continue
        if declared in limits and maximum != limits[declared]:
            violations.append(
                violation((*path, "maximum"), f"maximum is {maximum}, but {declared} allows {limits[declared]}.", "Correct the maximum or the format.")
            )
        if declared == "int64" and maximum <= INT32_MAX:
            violations.append(
                violation((*path, "format"), f"Format is int64, but maximum {maximum} fits in int32.", "Use format int32, or raise the maximum.")
            )
    check(violations)


# --- Endpoint conventions ------------------------------------------------------


@pytest.mark.parametrize("path,method,operation", OPERATIONS, ids=OPERATION_IDS)
def test_operation_is_documented(path, method, operation):
    violations = []
    here = operation_path(path, method)
    if not operation.get("summary"):
        violations.append(violation((*here, "summary"), "The operation has no summary.", "Add a summary."))
    if not operation.get("tags"):
        violations.append(violation((*here, "tags"), "The operation has no tags.", "Add a tag from the top-level tags list."))
    declared = {tag.get("name") for tag in SPEC.get("tags", [])}
    for tag in sorted(set(operation.get("tags", [])) - declared):
        violations.append(violation((*here, "tags"), f"Tag {tag} is not declared.", f"Add {tag} to the top-level tags list, or use a declared tag."))
    if "500" not in operation.get("responses", {}):
        violations.append(violation((*here, "responses"), "No 500 response is declared.", "Add a 500 response that references InternalServerError."))
    check(violations)


def test_all_declared_tags_are_used():
    used = {tag for _, _, operation in OPERATIONS for tag in operation.get("tags", [])}
    check(
        [
            violation(("tags", index), f"Tag {tag.get('name')} is not used by any operation.", "Use this tag, or remove it.")
            for index, tag in enumerate(SPEC.get("tags", []))
            if tag.get("name") not in used
        ]
    )


@pytest.mark.parametrize("path,method,operation", OPERATIONS, ids=OPERATION_IDS)
def test_path_parameters_match_the_template(path, method, operation):
    here = operation_path(path, method, "parameters")
    declared = {
        parameter.get("name"): parameter.get("required")
        for parameter in map(resolve, operation.get("parameters", []))
        if parameter.get("in") == "path"
    }
    template = set(re.findall(r"{(\w+)}", path))
    violations = [
        violation(here, f"{{{name}}} is in the path but is not declared.", f"Declare {name} as a path parameter.")
        for name in sorted(template - set(declared))
    ]
    violations += [
        violation(here, f"Path parameter {name} is not in the path template.", f"Add {{{name}}} to the path, or remove the parameter.")
        for name in sorted(set(declared) - template)
    ]
    violations += [
        violation(here, f"Path parameter {name} has required: {value}.", "Set required: true.")
        for name, value in declared.items()
        if name in template and value is not True
    ]
    check(violations)


@pytest.mark.parametrize("path,method,operation", V1_OPERATIONS, ids=V1_IDS)
def test_v1_operation_has_shared_contract(path, method, operation):
    violations = []
    here = operation_path(path, method)
    if operation.get("security") != [{"Bearer": []}]:
        violations.append(
            violation((*here, "security"), f"Found security {operation.get('security')}.", "Set security to a single Bearer entry with no scopes.")
        )
    for status in sorted({"400", "401", "403", "500"} - set(operation.get("responses", {}))):
        violations.append(violation((*here, "responses"), f"No {status} response is declared.", f"Add a {status} response that references the shared response."))
    missing = {"ApiVersionHeader", "CorrelationIdHeader"} - parameter_refs(operation)
    if missing:
        violations.append(violation((*here, "parameters"), f"Missing shared parameters: {sorted(missing)}.", required_header_fix(missing)))
    check(violations)


def test_bearer_security_scheme_is_jwt():
    here = ("components", "securitySchemes", "Bearer")
    scheme = COMPONENTS.get("securitySchemes", {}).get("Bearer", {})
    found = (scheme.get("type"), scheme.get("scheme"), scheme.get("bearerFormat"))
    check(
        []
        if found == ("http", "bearer", "JWT")
        else [violation(here, f"Found (type, scheme, bearerFormat) = {found}.", "Use type http, scheme bearer, and bearerFormat JWT.")]
    )


@pytest.mark.parametrize("resource", RESOURCES)
def test_resource_has_all_crud_operations(resource):
    paths = [path for path, _, _ in V1_OPERATIONS if path.split("/")[2] == resource]
    found = {
        (method, path.split("/")[3])
        for path, method, _ in V1_OPERATIONS
        if path.split("/")[2] == resource
    }
    expected = {("get", "get-all"), ("get", "get"), ("post", "add"), ("put", "update"), ("delete", "delete")}
    here = ("paths", paths[0])
    violations = [
        violation(here, f"/v1/{resource} has no {method.upper()} {action} operation.", f"Add a {method.upper()} /v1/{resource}/{action} operation.")
        for method, action in sorted(expected - found)
    ]
    violations += [
        violation(here, f"/v1/{resource} has an unexpected {method.upper()} {action} operation.", "Rename it to a standard action, or update this test if a new action was added on purpose.")
        for method, action in sorted(found - expected)
    ]
    check(violations)


def require_responses(path, method, operation, statuses):
    """Returns a violation for each required status that is not declared."""
    return [
        violation(operation_path(path, method, "responses"), f"No {status} response is declared.", f"Add a {status} response.")
        for status in sorted(statuses - set(operation.get("responses", {})))
    ]


@pytest.mark.parametrize("path,method,operation", v1_operations("get-all"))
def test_get_all_is_paged_and_returns_an_array(path, method, operation):
    violations = require_responses(path, method, operation, {"200", "204"})
    missing = {"PageQuery", "PageSizeQuery"} - parameter_refs(operation)
    if missing:
        violations.append(violation(operation_path(path, method, "parameters"), f"Missing paging parameters: {sorted(missing)}.", required_header_fix(missing)))
    schema = response_schema(operation, "200") or {}
    if schema.get("type") != "array":
        violations.append(violation(operation_path(path, method, "responses", "200"), f"The 200 response schema is {schema}.", "Return an array of the resource DTO."))
    check(violations)


@pytest.mark.parametrize("path,method,operation", v1_operations("get"))
def test_get_returns_a_dto_or_no_content(path, method, operation):
    violations = require_responses(path, method, operation, {"200", "204"})
    name = ref_name(response_schema(operation, "200"))
    if not (name or "").endswith("Dto"):
        violations.append(violation(operation_path(path, method, "responses", "200"), f"The 200 response schema is {name}.", "Reference the resource DTO schema."))
    check(violations)


@pytest.mark.parametrize("path,method,operation", v1_operations("add") + v1_operations("update"))
def test_writes_require_a_json_dto_body(path, method, operation):
    here = operation_path(path, method, "requestBody")
    body = operation.get("requestBody", {})
    violations = []
    if body.get("required") is not True:
        violations.append(violation((*here, "required"), f"Found required: {body.get('required')}.", "Declare a request body with required: true."))
    content = body.get("content", {})
    if set(content) != {"application/json", "application/*+json"}:
        violations.append(violation((*here, "content"), f"Found media types {sorted(content)}.", "Declare application/json and application/*+json."))
    names = {ref_name(media.get("schema")) for media in content.values()}
    if len(names) != 1 or not (next(iter(names)) or "").endswith("Dto"):
        violations.append(violation((*here, "content"), f"Found schemas {sorted(map(str, names))}.", "Reference the same resource DTO for every media type."))
    check(violations)


@pytest.mark.parametrize("path,method,operation", v1_operations("add"))
def test_add_returns_created_with_a_key(path, method, operation):
    violations = require_responses(path, method, operation, {"201"})
    name = ref_name(response_schema(operation, "201"))
    if "201" in operation.get("responses", {}) and not (name or "").startswith("AddResponse"):
        violations.append(violation(operation_path(path, method, "responses", "201"), f"The 201 response schema is {name}.", "Reference an AddResponse schema."))
    check(violations)


@pytest.mark.parametrize("path,method,operation", v1_operations("update") + v1_operations("delete"))
def test_update_and_delete_return_no_content(path, method, operation):
    violations = require_responses(path, method, operation, {"204"})
    for status in sorted({"200", "201"} & set(operation.get("responses", {}))):
        violations.append(violation(operation_path(path, method, "responses", status), f"A {status} response is declared.", "Remove it. These operations return 204."))
    check(violations)


@pytest.mark.parametrize("path,method,operation", OPERATIONS, ids=OPERATION_IDS)
def test_no_content_response_declares_no_body(path, method, operation):
    response = operation.get("responses", {}).get("204")
    if response is None:
        return
    name = ref_name(response)
    here = ("components", "responses", name) if name else operation_path(path, method, "responses", "204")
    check(
        [violation((*here, "content"), "A 204 response declares content, but it cannot have a body.", "Remove the content block.")]
        if "content" in resolve(response)
        else []
    )


# --- DTO sample payloads -------------------------------------------------------

VALID_PAYLOADS = [
    ("CategoriesDto", {"categoryName": "Beverages"}),
    ("CategoriesDto", {"categoryId": 1, "categoryName": "Beverages", "description": None, "picture": None}),
    ("CategoriesDto", {"categoryId": 1, "categoryName": "x" * 15}),
    ("CategoriesDto", {"categoryId": INT32_MAX, "categoryName": "Beverages"}),
    ("CustomersDto", {"customerId": "ALFKI", "companyName": "Alfreds Futterkiste"}),
    ("EmployeesDto", {"firstName": "Nancy", "lastName": "Davolio"}),
    ("EmployeesDto", {"firstName": "Nancy", "lastName": "Davolio", "birthDate": "1948-12-08T00:00:00Z", "reportsTo": 2}),
    ("OrderDetailsDto", {"orderId": 10248, "productId": 11, "unitPrice": 14, "quantity": 12, "discount": 0}),
    ("OrderDetailsDto", {"orderId": 10248, "productId": 11, "unitPrice": 14.5, "quantity": 12, "discount": 0.25}),
    ("OrderDetailsDto", {"orderId": 1, "productId": 1, "unitPrice": 0, "quantity": 32767, "discount": 1}),
    ("OrdersDto", {}),
    ("OrdersDto", {"orderId": 10248, "customerId": "VINET", "freight": 32.38, "orderDate": "1996-07-04T00:00:00Z", "shipVia": 3}),
    ("ProductsDto", {"productName": "Chai"}),
    ("ProductsDto", {"productName": "Chai", "unitPrice": 18, "unitsInStock": 0, "reorderLevel": 0, "discontinued": False}),
    ("ShippersDto", {"companyName": "Speedy Express"}),
    ("ShippersDto", {"shipperId": 1, "companyName": "Speedy Express", "phone": "(503) 555-9831"}),
    ("SuppliersDto", {"companyName": "Exotic Liquids"}),
    ("SuppliersDto", {"supplierId": 1, "companyName": "Exotic Liquids", "homePage": None}),
    ("AddResponseInt", {"id": 1}),
    ("AddResponseString", {"id": "ALFKI"}),
    ("AddResponseOrderDetails", {"orderId": 10248, "productId": 11}),
]

ORDER_DETAIL = {"orderId": 1, "productId": 1, "unitPrice": 1, "quantity": 1, "discount": 0}

INVALID_PAYLOADS = [
    ("CategoriesDto", {}, "missing categoryName"),
    ("CategoriesDto", {"categoryName": ""}, "empty categoryName"),
    ("CategoriesDto", {"categoryName": "x" * 16}, "categoryName too long"),
    ("CategoriesDto", {"categoryId": 0, "categoryName": "Beverages"}, "categoryId below minimum"),
    ("CategoriesDto", {"categoryId": INT32_MAX + 1, "categoryName": "Beverages"}, "categoryId above int32"),
    ("CategoriesDto", {"categoryId": "abc", "categoryName": "Beverages"}, "non-numeric categoryId"),
    ("CategoriesDto", {"categoryId": "1", "categoryName": "Beverages"}, "string categoryId"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "orderId": "1"}, "string orderId"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "quantity": "1"}, "string quantity"),
    ("ProductsDto", {"productName": "Chai", "unitsInStock": "1"}, "string unitsInStock"),
    ("OrdersDto", {"shipVia": "1"}, "string shipVia"),
    ("CustomersDto", {"customerId": "ALFKI"}, "missing companyName"),
    ("CustomersDto", {"customerId": "ALFK", "companyName": "A"}, "customerId too short"),
    ("CustomersDto", {"customerId": "ALFKIX", "companyName": "A"}, "customerId too long"),
    ("CustomersDto", {"customerId": None, "companyName": "A"}, "null customerId"),
    ("EmployeesDto", {"firstName": "Nancy"}, "missing lastName"),
    ("EmployeesDto", {"firstName": "x" * 11, "lastName": "Davolio"}, "firstName too long"),
    ("EmployeesDto", {"firstName": "N", "lastName": "D", "birthDate": "not-a-date"}, "malformed birthDate"),
    ("EmployeesDto", {"firstName": "N", "lastName": "D", "extension": "12345"}, "extension too long"),
    ("OrderDetailsDto", {k: v for k, v in ORDER_DETAIL.items() if k != "orderId"}, "missing orderId"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "discount": 1.5}, "discount above 1"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "discount": -0.1}, "negative discount"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "quantity": 0}, "quantity below 1"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "quantity": 32768}, "quantity above int16"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "unitPrice": -1}, "negative unitPrice"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "unitPrice": "1"}, "string unitPrice"),
    ("OrderDetailsDto", {**ORDER_DETAIL, "discount": "0.5"}, "string discount"),
    ("OrdersDto", {"freight": "1"}, "string freight"),
    ("ProductsDto", {"productName": "Chai", "unitPrice": "1"}, "string unitPrice"),
    ("OrdersDto", {"customerId": "ABC"}, "customerId too short"),
    ("OrdersDto", {"orderDate": "1996-13-45"}, "malformed orderDate"),
    ("OrdersDto", {"shipVia": 0}, "shipVia below minimum"),
    ("OrdersDto", {"shipCity": "x" * 16}, "shipCity too long"),
    ("ProductsDto", {}, "missing productName"),
    ("ProductsDto", {"productName": "Chai", "unitsInStock": 32768}, "unitsInStock above int16"),
    ("ProductsDto", {"productName": "Chai", "unitPrice": -1}, "negative unitPrice"),
    ("ProductsDto", {"productName": "Chai", "discontinued": "yes"}, "non-boolean discontinued"),
    ("ShippersDto", {}, "missing companyName"),
    ("ShippersDto", {"companyName": "x" * 41}, "companyName too long"),
    ("ShippersDto", {"companyName": "A", "phone": "x" * 25}, "phone too long"),
    ("SuppliersDto", {}, "missing companyName"),
    ("SuppliersDto", {"companyName": "A", "contactName": "x" * 31}, "contactName too long"),
    ("SuppliersDto", {"companyName": "A", "supplierId": -1}, "negative supplierId"),
    ("AddResponseOrderDetails", {"orderId": 1}, "missing productId"),
]


def schema_error_path(name, error):
    """Returns the specification path of the constraint a payload error came from."""
    here = ("components", "schemas", name)
    if error.validator == "required":
        return (*here, "required")
    for field in error.absolute_path:
        here = (*here, "properties", field)
    return (*here, error.validator)


def field_path(name, reason):
    """Returns the specification path of the field that a sample's reason names."""
    here = ("components", "schemas", name)
    properties = COMPONENTS["schemas"][name].get("properties", {})
    for word in reason.split():
        if word in properties:
            return (*here, "properties", word)
    return here


@pytest.mark.parametrize("schema,payload", VALID_PAYLOADS)
def test_schema_accepts_valid_payload(schema, payload):
    require_schema(schema)
    check(
        [
            violation(
                schema_error_path(schema, error),
                f"{schema} rejected the valid sample {payload}: {error.message}.",
                "Correct this constraint, or update VALID_PAYLOADS if the rule changed on purpose.",
            )
            for error in schema_validator(schema).iter_errors(payload)
        ]
    )


@pytest.mark.parametrize(
    "schema,payload,reason",
    [pytest.param(schema, payload, reason, id=f"{schema}: {reason}") for schema, payload, reason in INVALID_PAYLOADS],
)
def test_schema_rejects_invalid_payload(schema, payload, reason):
    require_schema(schema)
    here = field_path(schema, reason)
    definition = lookup(pointer(here))
    check(
        []
        if not schema_validator(schema).is_valid(payload)
        else [
            violation(
                here,
                f"{schema} accepted the sample {payload}, which should be rejected ({reason}). "
                f"This definition is currently {definition}. Required fields: {COMPONENTS['schemas'][schema].get('required', [])}.",
                "Restore the constraint, or update INVALID_PAYLOADS if the rule changed on purpose.",
            )
        ]
    )


@pytest.mark.parametrize("schema", ["AddResponseInt", "AddResponseString"])
def test_add_response_requires_its_key(schema):
    require_schema(schema)
    check(
        [
            violation(
                ("components", "schemas", schema),
                f"{schema} accepted an empty response. Its required list is {COMPONENTS['schemas'][schema].get('required', [])}.",
                "Add id to the required list of this schema.",
            )
        ]
        if schema_validator(schema).is_valid({})
        else []
    )
