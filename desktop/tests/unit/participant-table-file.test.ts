/** Authored interchange fixtures catch malformed study rows without partial replacement. */
import { describe, expect, it } from "vitest";
import { AVERAGE_COLUMNS, CLUSTER_COLUMNS, parseTable, serializeTable } from "../../src/renderer/pages/panels/_participants/tableFile";

describe("participant file import", () => {
  it("reads reordered BOM headers, quoted separators and escaped quotes with CRLF", () => {
    expect(parseTable('\uFEFFgroup,simulation_name,subject_id\r\n"Group, one","motor ""left""",101\r\n', AVERAGE_COLUMNS, ",")).toEqual([
      { subject_id: "101", simulation_name: 'motor "left"', group: "Group, one" },
    ]);
  });
  it("keeps repeated subjects and correlation values in a tab-separated study", () => {
    expect(parseTable("subject_id\tsimulation_name\tresponse\teffect_size\tweight\n101\tleft\t1\t-0.25\t2\n101\tright\t0\t\t\n", CLUSTER_COLUMNS, "\t")).toEqual([
      { subject_id: "101", simulation_name: "left", response: "1", effect_size: "-0.25", weight: "2" },
      { subject_id: "101", simulation_name: "right", response: "0", effect_size: "", weight: "" },
    ]);
  });
  it("accepts quoted multiline fields", () => {
    expect(parseTable('subject_id,simulation_name,group\n101,left,"one\ntwo"', AVERAGE_COLUMNS, ",")[0]?.group).toBe("one\ntwo");
  });
  it.each([
    "subject_id,simulation_name,group\n101,left,one\n102,right",
    "subject_id,simulation_name,group\n101,left,one\n,,",
    "subject_id,simulation_name,group\n101,left,one\n102,right,",
    'subject_id,simulation_name,group\n101,left,"one',
    'subject_id,simulation_name,group\n101,left,"one"junk',
    "subject_id,simulation_name,subject_id\n101,left,one",
    "subject_id,simulation_name,group,extra\n101,left,one,x",
    "subject_id,simulation_name,group\n",
  ])("rejects the whole malformed table: %s", (input) => {
    expect(() => parseTable(input, AVERAGE_COLUMNS, ",")).toThrow();
  });
  it.each(["2,1,1", "1,NaN,1", "1,Infinity,1", "1,0,-1", "1,0,0"])("rejects invalid response/effect/weight %s", (values) => {
    expect(() => parseTable(`subject_id,simulation_name,response,effect_size,weight\n101,left,${values}`, CLUSTER_COLUMNS, ",")).toThrow();
  });
});

describe("participant file export", () => {
  it("writes explicit headers, CRLF and standard doubled-quote escaping", () => {
    expect(serializeTable([{ subject_id: "101", simulation_name: 'left,"motor"', group: "Group1" }], AVERAGE_COLUMNS, ",")).toBe(
      'subject_id,simulation_name,group\r\n101,"left,""motor""",Group1\r\n',
    );
  });
  it("writes TSV including blank optional values", () => {
    expect(serializeTable([{ subject_id: "101", simulation_name: "left", response: "1" }], CLUSTER_COLUMNS, "\t")).toBe(
      "subject_id\tsimulation_name\tresponse\teffect_size\tweight\r\n101\tleft\t1\t\t\r\n",
    );
  });
});
