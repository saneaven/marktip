import * as tm from "./dist/marktip.js";

await tm.init();

const tone: tm.Attr = { type: "str", choices: ["note", "warning"], default: "note" };
const shade: tm.Attr = { type: "str", inherit: true };
const data: tm.Attr = { type: "StrMap" };
const mark: tm.MarkSpec = { name: "review", tag: "review", attrs: { tone, shade, data }, excludes: ["bold"] };
const node: tm.NodeSpec = { name: "callout", kind: "block", content: "block+", attrs: { tone, data } };
const mapValue: tm.AttrValue = { hp: "30", name: "리안" };
const mapNode: tm.TiptapNode = { type: "callout", attrs: { data: mapValue } };
const schema = new tm.Schema({
    marks: [mark, tm.UNDERLINE, tm.HIGHLIGHT, tm.SUBSCRIPT, tm.SUPERSCRIPT, tm.TEXT_STYLE],
    nodes: [node, tm.MENTION, ...tm.DETAILS, tm.INLINE_MATH, tm.BLOCK_MATH],
    coreAttrs: { ...tm.TEXT_ALIGN, ...tm.LINK_ATTRS, ...tm.IMAGE_SIZE, ...tm.TABLE_SPANS },
    blockImage: false,
});
const extended = schema.extend({
    marks: [{ name: "annotation", tag: "ann" }],
    coreAttrs: { paragraph: { annotation: { type: "str", default: "" } } },
    blockImage: true,
});
const style: tm.MarkSpec = tm.textStyle({
    backgroundColor: false, fontFamily: false, lineHeight: false, mergeNestedSpanStyles: false,
});
const alignment = tm.textAlign({ types: ["paragraph"], alignments: ["left", "right"], defaultAlignment: "left" });
const link = tm.linkAttrs({ target: null, rel: null, class: "link" });
const restoredSchema = tm.Schema.fromDict(schema.toDict());
const same: boolean = restoredSchema.equals(schema);
const marks: readonly tm.MarkSpec[] = schema.marks;
const nodes: readonly tm.NodeSpec[] = schema.nodes;
const coreAttrs: Record<string, Record<string, tm.Attr>> = schema.coreAttrs;
const blockImage: boolean = schema.blockImage;

const document = tm.fromMarkdown("<callout>\ntext", {
    schema,
    cjkFriendly: true,
    html: true,
    partial: true,
    keepSource: false,
    linkSchemes: ["https"],
    imageSchemes: ["https"],
    linkRelative: "path_only",
    imageRelative: "reject",
    rejectNodeTypes: ["image"],
});
const loaded = tm.load(document.dump(), { schema });
const edited = tm.fromDict(document.toDict(), { schema, strict: "exact", base: loaded });
tm.fromDict(document.toDict(), { schema, strict: "content" }).free();
const markdown: string = edited.toMarkdown({ canonical: true });
const version: string = tm.version;
JSON.stringify({ same, marks, nodes, coreAttrs, blockImage, style, alignment, link, markdown, version, mapNode });

try {
    tm.fromDict({ type: "unrecognized" });
} catch (error) {
    if (error instanceof tm.UnknownTypeError) {
        const fields: string[] = [error.type, error.kind, error.code, error.path, error.detail, error.message];
        JSON.stringify(fields);
    } else if (error instanceof tm.InvalidNodeError) {
        const field: string = error.field;
        JSON.stringify(field);
    } else if (error instanceof tm.ParseError || error instanceof tm.MarktipError) {
        const code: string = error.code;
        JSON.stringify(code);
    }
}

for (const value of [edited, loaded, document, extended, restoredSchema, schema]) value.free();
