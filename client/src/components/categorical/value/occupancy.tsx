import React from "react";
import { connect } from "react-redux";
import * as d3 from "d3";
import {
  Classes,
  Popover,
  PopoverInteractionKind,
  Position,
} from "@blueprintjs/core";

// @ts-expect-error ts-migrate(1238) FIXME: Unable to resolve signature of class decorator whe... Remove this comment to see the full error message
@connect((state) => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any --- FIXME: disabled temporarily on migrate to TS.
  schema: (state as any).annoMatrix?.schema,
}))
class Occupancy extends React.PureComponent {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any --- FIXME: disabled temporarily on migrate to TS.
  canvas: any;

  _WIDTH = 100;

  _HEIGHT = 11;

  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types --- FIXME: disabled temporarily on migrate to TS.
  createHistogram = () => {
    /*
          Knowing that colorScale is based off continous data,
          createHistogram fetches the continous data in relation to the cells releveant to the catagory value.
          It then seperates that data into 50 bins for drawing the mini-histogram
        */
    const {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'metadataField' does not exist on type 'R... Remove this comment to see the full error message
      metadataField,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'categoryData' does not exist on type 'Re... Remove this comment to see the full error message
      categoryData,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'colorData' does not exist on type 'Reado... Remove this comment to see the full error message
      colorData,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'categoryValue' does not exist on type 'R... Remove this comment to see the full error message
      categoryValue,
    } = this.props;
    if (!this.canvas) return;
    const groupBy = categoryData.col(metadataField);
    const col = colorData.icol(0);
    const range = col.summarize();
    const histogramMap = col.histogram(
      50,
      [range.min, range.max],
      groupBy
    ); /* Because the signature changes we really need different names for histogram to differentiate signatures  */
    const bins = histogramMap.has(categoryValue)
      ? histogramMap.get(categoryValue)
      : new Array(50).fill(0);
    const xScale = d3
      .scaleLinear()
      .domain([0, bins.length])
      .range([0, this._WIDTH]);
    const largestBin = Math.max(...bins);
    const yScale = d3
      .scaleLinear()
      .domain([0, largestBin])
      .range([0, this._HEIGHT]);
    const ctx = this.canvas.getContext("2d");
    ctx.fillStyle = "#000";
    let x;
    let y;
    const rectWidth = this._WIDTH / bins.length;
    for (let i = 0, { length } = bins; i < length; i += 1) {
      x = xScale(i);
      y = yScale(bins[i]);
      ctx.fillRect(x, this._HEIGHT - y, rectWidth, y);
    }
  };

  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types --- FIXME: disabled temporarily on migrate to TS.
  createOccupancyStack = () => {
    /*
          Knowing that the color scale is based off of catagorical data,
          createOccupancyStack obtains a map showing the number if cells per colored value
          Using the colorScale a stack of colored bars is drawn representing the map
         */
    const {
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'metadataField' does not exist on type 'R... Remove this comment to see the full error message
      metadataField,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'categoryData' does not exist on type 'Re... Remove this comment to see the full error message
      categoryData,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'colorAccessor' does not exist on type 'R... Remove this comment to see the full error message
      colorAccessor,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'categoryValue' does not exist on type 'R... Remove this comment to see the full error message
      categoryValue,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'colorTable' does not exist on type 'Read... Remove this comment to see the full error message
      colorTable,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'schema' does not exist on type 'Readonly... Remove this comment to see the full error message
      schema,
      // @ts-expect-error ts-migrate(2339) FIXME: Property 'colorData' does not exist on type 'Reado... Remove this comment to see the full error message
      colorData,
    } = this.props;
    const { scale: colorScale } = colorTable;
    const ctx = this.canvas?.getContext("2d");
    if (!ctx) return;
    const groupBy = categoryData.col(metadataField);
    const occupancyMap = colorData
      .col(colorAccessor)
      .histogramCategorical(groupBy);
    const occupancy = occupancyMap.get(categoryValue);
    if (occupancy && occupancy.size > 0) {
      // not all categories have occupancy, so occupancy may be undefined.
      const x = d3
        .scaleLinear()
        /* get all the keys d[1] as an array, then find the sum */
        .domain([0, d3.sum(Array.from(occupancy.values()))])
        .range([0, this._WIDTH]);
      const categories =
        schema.annotations.obsByName[colorAccessor]?.categories;
      let currentOffset = 0;
      const dfColumn = colorData.col(colorAccessor);
      const categoryValues = dfColumn.summarizeCategorical().categories;
      let o;
      let scaledValue;
      let value;
      for (let i = 0, { length } = categoryValues; i < length; i += 1) {
        value = categoryValues[i];
        o = occupancy.get(value);
        scaledValue = x(o);
        ctx.fillStyle = o
          ? colorScale(categories.indexOf(value))
          : "rgb(255,255,255)";
        ctx.fillRect(currentOffset, 0, o ? scaledValue : 0, this._HEIGHT);
        currentOffset += o ? scaledValue : 0;
      }
    }
  };

  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types --- FIXME: disabled temporarily on migrate to TS.
  render() {
    // @ts-expect-error ts-migrate(2339) FIXME: Property 'colorAccessor' does not exist on type 'R... Remove this comment to see the full error message
    const { colorAccessor, categoryValue, colorByIsCategorical } = this.props;
    const { canvas } = this;
    if (canvas)
      canvas.getContext("2d").clearRect(0, 0, this._WIDTH, this._HEIGHT);
    return (
      <Popover
        interactionKind={PopoverInteractionKind.HOVER_TARGET_ONLY}
        hoverOpenDelay={1500}
        hoverCloseDelay={200}
        position={Position.LEFT}
        modifiers={{
          preventOverflow: { enabled: false },
          hide: { enabled: false },
        }}
        lazy
        usePortal
        disabled={colorByIsCategorical}
        popoverClassName={Classes.POPOVER_CONTENT_SIZING}
      >
        <canvas
          className={Classes.POPOVER_TARGET}
          style={{
            marginRight: 5,
            width: this._WIDTH,
            height: this._HEIGHT,
            borderBottom: colorByIsCategorical
              ? ""
              : "solid rgb(230, 230, 230) 0.25px",
          }}
          width={this._WIDTH}
          height={this._HEIGHT}
          ref={(ref) => {
            this.canvas = ref;
            if (colorByIsCategorical) this.createOccupancyStack();
            else this.createHistogram();
          }}
        />
        <div key="text" style={{ fontSize: "14px" }}>
          <p style={{ margin: "0" }}>
            This histograms shows the distribution of{" "}
            <strong>{colorAccessor}</strong> within{" "}
            <strong>{categoryValue}</strong>.
            <br />
            <br />
            The x axis is the same for each histogram, while the y axis is
            scaled to the largest bin within this histogram instead of the
            largest bin within the whole category.
          </p>
        </div>
      </Popover>
    );
  }
}

export default Occupancy;
