import numpy as np
from numpy.testing import assert_allclose
import pytest
import scipy as sp
from scipy import linalg, optimize, sparse

from sklearn.linear_model.glm import (
    Link,
    IdentityLink,
    LogLink,
    TweedieDistribution,
    NormalDistribution, PoissonDistribution,
    GammaDistribution, InverseGaussianDistribution,
    GeneralizedHyperbolicSecant,
    GeneralizedLinearRegressor)
from sklearn.linear_model import ElasticNet, Ridge

from sklearn.utils.testing import (
    assert_equal, assert_almost_equal,
    assert_array_equal, assert_array_almost_equal)


@pytest.mark.parametrize('link', Link.__subclasses__())
def test_link_properties(link):
    """Test link inverse and derivative."""
    rng = np.random.RandomState(0)
    x = rng.rand(100)*100
    link = link()  # instatiate object
    assert_almost_equal(link.link(link.inverse(x)), x, decimal=10)
    assert_almost_equal(link.inverse_derivative(link.link(x)),
                        1/link.derivative(x), decimal=10)


@pytest.mark.parametrize(
    'family, expected',
    [(NormalDistribution(), [True, True, True]),
     (PoissonDistribution(), [False, True, True]),
     (TweedieDistribution(power=1.5), [False, True, True]),
     (GammaDistribution(), [False, False, True]),
     (InverseGaussianDistribution(), [False, False, True]),
     (TweedieDistribution(power=4.5), [False, False, True])])
def test_family_bounds(family, expected):
    """Test the valid range of distributions at -1, 0, 1."""
    result = family.in_y_range([-1, 0, 1])
    assert_array_equal(result, expected)


@pytest.mark.parametrize(
    'family, chk_values',
    [(NormalDistribution(), [-1.5, -0.1, 0.1, 2.5]),
     (PoissonDistribution(), [0.1, 1.5]),
     (GammaDistribution(), [0.1, 1.5]),
     (InverseGaussianDistribution(), [0.1, 1.5]),
     (TweedieDistribution(power=-2.5), [0.1, 1.5]),
     (TweedieDistribution(power=-1), [0.1, 1.5]),
     (TweedieDistribution(power=1.5), [0.1, 1.5]),
     (TweedieDistribution(power=2.5), [0.1, 1.5]),
     (TweedieDistribution(power=-4), [0.1, 1.5]),
     (GeneralizedHyperbolicSecant(), [0.1, 1.5])])
def test_deviance_zero(family, chk_values):
    """Test deviance(y,y) = 0 for different families."""
    for x in chk_values:
        assert_almost_equal(family.deviance(x, x), 0, decimal=10)


@pytest.mark.parametrize(
    'family, link',
    [(NormalDistribution(), IdentityLink()),
     (PoissonDistribution(), LogLink()),
     (GammaDistribution(), LogLink()),
     (InverseGaussianDistribution(), LogLink()),
     (TweedieDistribution(power=1.5), LogLink()),
     (TweedieDistribution(power=4.5), LogLink())])
def test_fisher_matrix(family, link):
    """Test the Fisher matrix numerically.
    Trick: Use numerical differentiation with y = mu"""
    rng = np.random.RandomState(0)
    coef = np.array([-2, 1, 0, 1, 2.5])
    phi = 0.5
    X = rng.randn(10, 5)
    lin_pred = np.dot(X, coef)
    mu = link.inverse(lin_pred)
    weights = rng.randn(10)**2 + 1
    fisher = family._fisher_matrix(coef=coef, phi=phi, X=X, y=mu,
                                   weights=weights, link=link)
    approx = np.array([]).reshape(0, coef.shape[0])
    for i in range(coef.shape[0]):
        def f(coef):
            return -family._score(coef=coef, phi=phi, X=X, y=mu,
                                  weights=weights, link=link)[i]
        approx = np.vstack(
            [approx, sp.optimize.approx_fprime(xk=coef, f=f, epsilon=1e-5)])
    assert_allclose(fisher, approx, rtol=1e-3)


def test_sample_weights_validation():
    """Test the raised errors in the validation of sample_weight."""
    # 1. scalar value but not positive
    X = [[1]]
    y = [1]
    weights = 0
    glm = GeneralizedLinearRegressor(fit_intercept=False)
    with pytest.raises(ValueError):
        glm.fit(X, y, weights)

    # 2. 2d array
    weights = [[0]]
    with pytest.raises(ValueError):
        glm.fit(X, y, weights)

    # 3. 1d but wrong length
    weights = [1, 0]
    with pytest.raises(ValueError):
        glm.fit(X, y, weights)

    # 4. 1d but only zeros (sum not greater than 0)
    weights = [0, 0]
    X = [[0], [1]]
    y = [1, 2]
    with pytest.raises(ValueError):
        glm.fit(X, y, weights)

    # 5. 1d but weith a negative value
    weights = [2, -1]
    with pytest.raises(ValueError):
        glm.fit(X, y, weights)


def test_glm_family_argument():
    """Test GLM family argument set as string."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    for (f, fam) in [('normal', NormalDistribution()),
                     ('poisson', PoissonDistribution()),
                     ('gamma', GammaDistribution()),
                     ('inverse.gaussian', InverseGaussianDistribution())]:
        glm = GeneralizedLinearRegressor(family=f, alpha=0).fit(X, y)
        assert_equal(type(glm._family_instance), type(fam))

    glm = GeneralizedLinearRegressor(family='not a family',
                                     fit_intercept=False)
    with pytest.raises(ValueError):
        glm.fit(X, y)


def test_glm_link_argument():
    """Test GLM link argument set as string."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    for (l, link) in [('identity', IdentityLink()),
                      ('log', LogLink())]:
        glm = GeneralizedLinearRegressor(family='normal', link=l).fit(X, y)
        assert_equal(type(glm._link_instance), type(link))

    glm = GeneralizedLinearRegressor(family='normal', link='not a link')
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('alpha', ['not a number', -4.2])
def test_glm_alpha_argument(alpha):
    """Test GLM for invalid alpha argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(family='normal', alpha=alpha)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('l1_ratio', ['not a number', -4.2, 1.1, [1]])
def test_glm_l1_ratio_argument(l1_ratio):
    """Test GLM for invalid l1_ratio argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(family='normal', l1_ratio=l1_ratio)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('P1', [['a string', 'a string'], [1, [2]], [1, 2, 3],
                                [-1]])
def test_glm_P1_argument(P1):
    """Test GLM for invalid P1 argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(P1=P1, l1_ratio=0.5, check_input=True)
    with pytest.raises((ValueError, TypeError)):
        glm.fit(X, y)


@pytest.mark.parametrize('P2', ['a string', [1, 2, 3], [[2, 3]],
                                sparse.csr_matrix([1, 2, 3]), [-1]])
def test_glm_P2_argument(P2):
    """Test GLM for invalid P2 argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(P2=P2, check_input=True)
    with pytest.raises(ValueError):
        glm.fit(X, y)


def test_glm_P2_positive_semidefinite():
    """Test GLM for a positive semi-definite P2 argument."""
    n_samples, n_features = 10, 5
    rng = np.random.RandomState(42)
    y = np.arange(n_samples)
    X = np.zeros((n_samples, n_features))
    P2 = np.diag([100, 10, 5, 0, -1E-5])
    # construct random orthogonal matrix Q
    Q, R = linalg.qr(rng.randn(n_features, n_features))
    P2 = Q.T @ P2 @ Q
    glm = GeneralizedLinearRegressor(P2=P2, fit_intercept=False,
                                     check_input=True)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('fit_intercept', ['not bool', 1, 0, [True]])
def test_glm_fit_intercept_argument(fit_intercept):
    """Test GLM for invalid fit_intercept argument."""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(fit_intercept=fit_intercept)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('solver, l1_ratio',
                         [('not a solver', 0), (1, 0), ([1], 0),
                          ('irls', 0.5), ('lbfgs', 0.5), ('newton-cg', 0.5)])
def test_glm_solver_argument(solver, l1_ratio):
    """Test GLM for invalid solver argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(solver=solver, l1_ratio=l1_ratio)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('max_iter', ['not a number', 0, -1, 5.5, [1]])
def test_glm_max_iter_argument(max_iter):
    """Test GLM for invalid max_iter argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(max_iter=max_iter)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('tol', ['not a number', 0, -1.0, [1e-3]])
def test_glm_tol_argument(tol):
    """Test GLM for invalid tol argument."""
    y = np.array([1, 2])
    X = np.array([[1], [2]])
    glm = GeneralizedLinearRegressor(tol=tol)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('warm_start', ['not bool', 1, 0, [True]])
def test_glm_warm_start_argument(warm_start):
    """Test GLM for invalid warm_start argument."""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(warm_start=warm_start)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('start_params',
                         ['not a start_params', ['zero'], [0, 0, 0],
                          [[0, 0]], ['a', 'b']])
def test_glm_start_params_argument(start_params):
    """Test GLM for invalid start_params argument."""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(start_params=start_params)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('selection', ['not a selection', 1, 0, ['cyclic']])
def test_glm_selection_argument(selection):
    """Test GLM for invalid selection argument"""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(selection=selection)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('random_state', ['a string', 0.5, [0]])
def test_glm_random_state_argument(random_state):
    """Test GLM for invalid random_state argument."""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(random_state=random_state)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('copy_X', ['not bool', 1, 0, [True]])
def test_glm_copy_X_argument(copy_X):
    """Test GLM for invalid copy_X arguments."""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(copy_X=copy_X)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize('check_input', ['not bool', 1, 0, [True]])
def test_glm_check_input_argument(check_input):
    """Test GLM for invalid check_input argument."""
    y = np.array([1, 2])
    X = np.array([[1], [1]])
    glm = GeneralizedLinearRegressor(check_input=check_input)
    with pytest.raises(ValueError):
        glm.fit(X, y)


@pytest.mark.parametrize(
    'family',
    [NormalDistribution(), PoissonDistribution(),
     GammaDistribution(), InverseGaussianDistribution(),
     TweedieDistribution(power=1.5), TweedieDistribution(power=4.5),
     GeneralizedHyperbolicSecant()])
@pytest.mark.parametrize('solver', ['irls', 'lbfgs', 'newton-cg', 'cd'])
def test_glm_identiy_regression(family, solver):
    """Test GLM regression with identity link on a simple dataset."""
    coef = [1, 2]
    X = np.array([[1, 1, 1, 1, 1], [0, 1, 2, 3, 4]]).T
    y = np.dot(X, coef)
    glm = GeneralizedLinearRegressor(alpha=0, family=family,
                                     fit_intercept=False, solver=solver)
    res = glm.fit(X, y)
    assert_array_almost_equal(res.coef_, coef)


@pytest.mark.parametrize(
    'family',
    [NormalDistribution(), PoissonDistribution(),
     GammaDistribution(), InverseGaussianDistribution(),
     TweedieDistribution(power=1.5), TweedieDistribution(power=4.5),
     GeneralizedHyperbolicSecant()])
@pytest.mark.parametrize('solver', ['irls', 'lbfgs', 'newton-cg', 'cd'])
def test_glm_log_regression(family, solver):
    """Test GLM regression with log link on a simple dataset."""
    coef = [1, 2]
    X = np.array([[1, 1, 1, 1, 1], [0, 1, 2, 3, 4]]).T
    y = np.exp(np.dot(X, coef))
    glm = GeneralizedLinearRegressor(
                alpha=0, family=family, link=LogLink(), fit_intercept=False,
                solver=solver, start_params='least_squares')
    res = glm.fit(X, y)
    assert_array_almost_equal(res.coef_, coef)


@pytest.mark.filterwarnings('ignore::DeprecationWarning')
@pytest.mark.parametrize('solver', ['irls', 'lbfgs', 'newton-cg', 'cd'])
def test_normal_ridge(solver):
    """Test ridge regression for Normal distributions.

    Compare to test_ridge in test_ridge.py.
    """
    rng = np.random.RandomState(0)
    alpha = 1.0

    # 1. With more samples than features
    n_samples, n_features, n_predict = 10, 5, 10
    y = rng.randn(n_samples)
    X = rng.randn(n_samples, n_features)
    T = rng.randn(n_predict, n_features)

    # GLM has 1/(2*n) * Loss + 1/2*L2, Ridge has Loss + L2
    ridge = Ridge(alpha=alpha*n_samples, fit_intercept=True, tol=1e-6,
                  solver='svd', normalize=False)
    ridge.fit(X, y)
    glm = GeneralizedLinearRegressor(alpha=1.0, l1_ratio=0, family='normal',
                                     link='identity', fit_intercept=True,
                                     tol=1e-6, max_iter=100, solver=solver,
                                     random_state=42)
    glm.fit(X, y)
    assert_equal(glm.coef_.shape, (X.shape[1], ))
    assert_array_almost_equal(glm.coef_, ridge.coef_)
    assert_almost_equal(glm.intercept_, ridge.intercept_)
    assert_array_almost_equal(glm.predict(T), ridge.predict(T))

    ridge = Ridge(alpha=alpha*n_samples, fit_intercept=False, tol=1e-6,
                  solver='svd', normalize=False)
    ridge.fit(X, y)
    glm = GeneralizedLinearRegressor(alpha=1.0, l1_ratio=0, family='normal',
                                     link='identity', fit_intercept=False,
                                     tol=1e-6, max_iter=100, solver=solver,
                                     random_state=42, fit_dispersion='chisqr')
    glm.fit(X, y)
    assert_equal(glm.coef_.shape, (X.shape[1], ))
    assert_array_almost_equal(glm.coef_, ridge.coef_)
    assert_almost_equal(glm.intercept_, ridge.intercept_)
    assert_array_almost_equal(glm.predict(T), ridge.predict(T))
    mu = glm.predict(X)
    assert_almost_equal(glm.dispersion_,
                        np.sum((y-mu)**2/(n_samples-n_features)))

    # 2. With more features than samples and sparse
    n_samples, n_features, n_predict = 5, 10, 10
    y = rng.randn(n_samples)
    X = sparse.csr_matrix(rng.randn(n_samples, n_features))
    T = sparse.csr_matrix(rng.randn(n_predict, n_features))

    # GLM has 1/(2*n) * Loss + 1/2*L2, Ridge has Loss + L2
    ridge = Ridge(alpha=alpha*n_samples, fit_intercept=True, tol=1e-9,
                  solver='sag', normalize=False, max_iter=100000)
    ridge.fit(X, y)
    glm = GeneralizedLinearRegressor(alpha=1.0, l1_ratio=0, tol=1e-8,
                                     family='normal', link='identity',
                                     fit_intercept=True, solver=solver,
                                     max_iter=300, random_state=42)
    glm.fit(X, y)
    assert_equal(glm.coef_.shape, (X.shape[1], ))
    assert_array_almost_equal(glm.coef_, ridge.coef_, decimal=5)
    assert_almost_equal(glm.intercept_, ridge.intercept_, decimal=5)
    assert_array_almost_equal(glm.predict(T), ridge.predict(T), decimal=5)

    ridge = Ridge(alpha=alpha*n_samples, fit_intercept=False, tol=1e-7,
                  solver='sag', normalize=False, max_iter=1000)
    ridge.fit(X, y)
    glm = GeneralizedLinearRegressor(alpha=1.0, l1_ratio=0, tol=1e-7,
                                     family='normal', link='identity',
                                     fit_intercept=False, solver=solver)
    glm.fit(X, y)
    assert_equal(glm.coef_.shape, (X.shape[1], ))
    assert_array_almost_equal(glm.coef_, ridge.coef_)
    assert_almost_equal(glm.intercept_, ridge.intercept_)
    assert_array_almost_equal(glm.predict(T), ridge.predict(T))


def test_poisson_ridge():
    """Test ridge regression with poisson family and LogLink.

    Compare to R's glmnet"""
    # library("glmnet")
    # options(digits=10)
    # df <- data.frame(a=c(-2,-1,1,2), b=c(0,0,1,1), y=c(0,1,1,2))
    # x <- data.matrix(df[,c("a", "b")])
    # y <- df$y
    # fit <- glmnet(x=x, y=y, alpha=0, intercept=T, family="poisson",
    #               standardize=F, thresh=1e-10, nlambda=10000)
    # coef(fit, s=1)
    # (Intercept) -0.12889386979
    # a            0.29019207995
    # b            0.03741173122
    X = np.array([[-2, -1, 1, 2], [0, 0, 1, 1]]).T
    y = np.array([0, 1, 1, 2])
    s_dec = {'irls': 7, 'lbfgs': 5, 'newton-cg': 5, 'cd': 7}
    s_tol = {'irls': 1e-8, 'lbfgs': 1e-7, 'newton-cg': 1e-7, 'cd': 1e-8}
    for solver in ['irls', 'lbfgs', 'newton-cg', 'cd']:
        glm = GeneralizedLinearRegressor(alpha=1, l1_ratio=0,
                                         fit_intercept=True, family='poisson',
                                         link='log', tol=s_tol[solver],
                                         solver=solver, max_iter=300,
                                         random_state=42)
        glm.fit(X, y)
        assert_almost_equal(glm.intercept_, -0.12889386979,
                            decimal=s_dec[solver])
        assert_array_almost_equal(glm.coef_, [0.29019207995, 0.03741173122],
                                  decimal=s_dec[solver])


def test_normal_enet():
    """Test elastic net regression with normal/gaussian family."""
    rng = np.random.RandomState(0)
    alpha, l1_ratio = 0.3, 0.7
    n_samples, n_features = 20, 2
    X = rng.randn(n_samples, n_features).copy(order='F')
    beta = rng.randn(n_features)
    y = 2 + np.dot(X, beta) + rng.randn(n_samples)

    glm = GeneralizedLinearRegressor(alpha=alpha, l1_ratio=l1_ratio,
                                     family='normal', link='identity',
                                     fit_intercept=True, tol=1e-8,
                                     max_iter=100, selection='cyclic',
                                     solver='cd', start_params='zero',
                                     check_input=False)
    glm.fit(X, y)

    enet = ElasticNet(alpha=alpha, l1_ratio=l1_ratio, fit_intercept=True,
                      normalize=False, tol=1e-8, copy_X=True)
    enet.fit(X, y)

    assert_almost_equal(glm.intercept_, enet.intercept_, decimal=7)
    assert_array_almost_equal(glm.coef_, enet.coef_, decimal=7)


def test_poisson_enet():
    """Test elastic net regression with poisson family and LogLink.

    Compare to R's glmnet"""
    # library("glmnet")
    # options(digits=10)
    # df <- data.frame(a=c(-2,-1,1,2), b=c(0,0,1,1), y=c(0,1,1,2))
    # x <- data.matrix(df[,c("a", "b")])
    # y <- df$y
    # fit <- glmnet(x=x, y=y, alpha=0.5, intercept=T, family="poisson",
    #               standardize=F, thresh=1e-10, nlambda=10000)
    # coef(fit, s=1)
    # (Intercept) -0.03550978409
    # a            0.16936423283
    # b            .
    glmnet_intercept = -0.03550978409
    glmnet_coef = [0.16936423283, 0.]
    X = np.array([[-2, -1, 1, 2], [0, 0, 1, 1]]).T
    y = np.array([0, 1, 1, 2])
    glm = GeneralizedLinearRegressor(alpha=1, l1_ratio=0.5, family='poisson',
                                     link='log', solver='cd', tol=1e-8,
                                     selection='random', random_state=42)
    glm.fit(X, y)
    assert_almost_equal(glm.intercept_, glmnet_intercept, decimal=7)
    assert_array_almost_equal(glm.coef_, glmnet_coef, decimal=7)

    # test results with general optimization procedure
    def obj(coef):
        pd = PoissonDistribution()
        link = LogLink()
        N = y.shape[0]
        mu = link.inverse(X @ coef[1:]+coef[0])
        alpha, l1_ratio = (1, 0.5)
        return 1./(2.*N) * pd.deviance(y, mu) \
            + 0.5 * alpha * (1-l1_ratio) * (coef[1:]**2).sum() \
            + alpha * l1_ratio * np.sum(np.abs(coef[1:]))
    res = optimize.minimize(obj, [0, 0, 0], method='nelder-mead', tol=1e-10,
                            options={'maxiter': 1000, 'disp': False})
    assert_almost_equal(glm.intercept_, res.x[0], decimal=5)
    assert_almost_equal(glm.coef_, res.x[1:], decimal=5)
    assert_almost_equal(obj(np.concatenate(([glm.intercept_], glm.coef_))),
                        res.fun, decimal=8)

    # same for start_params='zero' and selection='cyclic'
    # with reduced precision
    glm = GeneralizedLinearRegressor(alpha=1, l1_ratio=0.5, family='poisson',
                                     link='log', solver='cd', tol=1e-5,
                                     selection='cyclic', start_params='zero')
    glm.fit(X, y)
    assert_almost_equal(glm.intercept_, glmnet_intercept, decimal=4)
    assert_array_almost_equal(glm.coef_, glmnet_coef, decimal=4)

    # start_params='least_squares' with different alpha
    glm = GeneralizedLinearRegressor(alpha=0.005, l1_ratio=0.5,
                                     family='poisson',
                                     link='log', solver='cd', tol=1e-5,
                                     start_params='zero')
    glm.fit(X, y)
    # warm start with original alpha and use of sparse matrices
    glm.warm_start = True
    glm.alpha = 1
    X = sparse.csr_matrix(X)
    glm.fit(X, y)
    assert_almost_equal(glm.intercept_, glmnet_intercept, decimal=4)
    assert_array_almost_equal(glm.coef_, glmnet_coef, decimal=4)
