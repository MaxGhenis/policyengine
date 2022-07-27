import React from 'react';
import { Collapse, Alert, Table, Tooltip, Radio } from 'antd';
import { Chart } from "./chart";
import prettyMilliseconds from "pretty-ms";
import { Row } from "react-bootstrap";
import { CountryContext } from '../../../countries';
import Spinner from '../../general/spinner';

const { Panel } = Collapse;

export default class AgeChart extends React.Component {
    // The age chart is an optional microsimulation output, showing the effect
    // of a given reform on each age group.
    static contextType = CountryContext;

    constructor(props) {
        super(props);
        this.state = {
            error: false,
        }
        this.fetchResults = this.fetchResults.bind(this);
    }

    fetchResults() {
        let url = new URL(`${this.context.apiURL}/age-chart`);
		this.context.setState({ waitingOnAgeChart: true }, () => {
			fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(submission)
            })
				.then((res) => {
					if (res.ok) {
						return res.json();
					} else {
						throw res;
					}
				}).then((data) => {
					this.setState({ error: false });
                    this.context.setState({ageChartResult: data, waitingOnAgeChart: false, ageChartIsOutdated: false});
				}).catch(e => {
                    this.context.setState({ waitingOnAgeChart: false});
					this.setState({ error: true });
				});
		});
    }

    render() {
        const results = this.context.ageChartResult;
        return (
            <Collapse ghost onChange={open => {if(open && (!results || this.context.ageChartIsOutdated)) { this.fetchResults(); }}}>
                <Panel header="Impact by age" key="1">
                    {
                        (this.context.waitingOnAgeChart || (!this.state.error && !results)) ?
                            <Spinner /> :
                            this.state.error ?
                                <Alert type="error" message="Something went wrong." /> :
                                <>
                                    <Row>
                                        <Chart plot={results.age_chart} md={12}/>
                                    </Row>
                                </>
                    }
                </Panel>
            </Collapse>
        );
    }
    
}