/**
 * The function will split string by comma or space, return unique non-empty strings
 * @param geneString - a string of comma delimited genes
 * @returns an array
 */
import pull from "lodash.pull";
import uniq from "lodash.uniq";

// eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types, @typescript-eslint/no-explicit-any -- - FIXME: disabled temporarily on migrate to TS.
export default function parseBulkGeneString(geneString: any) {
  return pull(uniq(geneString.split(/[ ,]+/)), "");
}
