import React from 'react';
import { connect } from 'react-redux';

import RegistrationForm from '../Account/RegistrationForm';
import * as accountActions from '../../actions/account';


export const Home = React.createClass({
  render: function() {
    return (
      <div>
        <h2>Welcome.</h2>
        <RegistrationForm accountRegister={this.props.accountRegister} />
      </div>
    )
  }
});

function mapStateToProps(state) {
  return {};
}

export const HomeContainer = connect(
  mapStateToProps,
  accountActions
)(Home);

